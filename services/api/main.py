import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError, model_validator

from services.review_signals import load_policy, resolve_policy_metadata
from services.storage.db import DomainError, PROFILES, ROOT, Store, profile_for
import services.sensitivity  # Ensure sensitivity dependency (regex) validates at API startup.


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')


class InputItem(Body):
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Reference(Body):
    source: str
    sentiment_column: str | None = None
    topic_column: str | None = None
    sentiment_map: dict[str, int] = Field(default_factory=dict)
    topic_map: dict[str, int] = Field(default_factory=dict)


class DatasetInput(Body):
    name: str
    profile: str
    preview_id: str | None = None
    text_column: str | None = None
    skip_invalid: bool = False
    reference: Reference | None = None
    items: list[InputItem] | None = None


class NameInput(Body):
    name: str


class CopyInput(NameInput):
    profile: str


class ItemsInput(Body):
    items: list[InputItem]


class RunInput(Body):
    dataset_id: str


class QuickInput(Body):
    profile: str
    text: str


class EditInput(Body):
    text: str
    expected_revision: int = Field(ge=1)


class ReviewInput(Body):
    task: Literal['sentiment','topic']
    status: Literal['unreviewed','confirmed','corrected']
    label_id: int | None = None
    note: str = ''
    expected_revision: int = Field(ge=1)
    expected_review_revision: int = Field(ge=0)
    run_id: str | None = None
    source_prediction_id: str | None = None


class RestoreInput(Body):
    task: Literal['sentiment','topic']
    review_revision: int = Field(ge=1)
    expected_revision: int = Field(ge=1)
    expected_review_revision: int = Field(ge=0)
    revision_id: str | None = None


class Filters(Body):
    run_id: str | None = None
    label_source: Literal['effective','ai'] = 'effective'
    q: str | None = None
    item_ids: str | None = None
    sentiment: int | None = None
    topic: int | None = None
    review_status: Literal['all','unreviewed','partial','reviewed','needs_review'] = 'all'
    review_signal: Literal['all','model_uncertain','sentiment_uncertain','topic_uncertain','truncated','pending_signal_review'] = 'all'
    sort: Literal['source_row','text','sentiment','topic'] = 'source_row'
    direction: Literal['asc','desc'] = 'asc'


class ExportInput(Filters):
    scope: Literal['all','filtered'] = 'filtered'


class SensitivitySelectionInput(Body):
    start_utf16: StrictInt
    end_utf16: StrictInt
    text: StrictStr


class SensitivityExperimentInput(Body):
    revision_id: StrictStr
    expected_revision: StrictInt = Field(ge=1)
    text_sha256: StrictStr
    run_id: StrictStr | None = None
    source_prediction_id: StrictStr | None
    selection: SensitivitySelectionInput


class ExplanationInput(Body):
    source_prediction_id: StrictStr


class AttributionTargetInput(Body):
    kind: Literal['polarity_margin', 'label_score']
    label_id: StrictInt | None = None

    @model_validator(mode='after')
    def validate_target(self):
        if self.kind == 'label_score' and self.label_id is None:
            raise ValueError('label_id is required when kind is label_score')
        if self.kind == 'polarity_margin' and self.label_id is not None:
            raise ValueError('label_id must be None when kind is polarity_margin')
        return self


class AttributionRequestInput(Body):
    source_prediction_id: StrictStr
    target: AttributionTargetInput


def check_origin(request: Request):
    origin = request.headers.get('origin')
    if origin:
        host = request.headers.get('host')
        from urllib.parse import urlparse
        parsed_origin = urlparse(origin)
        parsed_host = urlparse('//'+(host or ''))
        aliases = {'localhost': '127.0.0.1', '127.0.0.1': '127.0.0.1'}
        try:
            allowed = (parsed_origin.scheme in ('http', 'https')
                and not parsed_origin.username and not parsed_origin.password
                and parsed_origin.path in ('', '/') and not parsed_origin.query and not parsed_origin.fragment
                and aliases.get(parsed_origin.hostname, parsed_origin.hostname) == aliases.get(parsed_host.hostname, parsed_host.hostname)
                and (parsed_origin.port or (443 if parsed_origin.scheme == 'https' else 80)) == (parsed_host.port or (443 if request.url.scheme == 'https' else 80))
                and parsed_origin.scheme == request.url.scheme)
        except ValueError:
            allowed = False
        if not allowed:
            raise DomainError('FORBIDDEN_ORIGIN', 'Origin không được phép.', 403)


def create_app(runtime_dir=None, registry=None, start_worker=False, explanation_service=None, explanation_provider=None):
    load_policy()
    store = Store(runtime_dir)
    if registry is None:
        from services.inference.registry import ModelRegistry
        registry = ModelRegistry(store.runtime / 'models')
    worker = None
    if start_worker:
        from services.worker import Worker
        worker = Worker(store.runtime, registry)

    @asynccontextmanager
    async def lifespan(app):
        store.cleanup()
        thread = None
        if worker:
            thread = threading.Thread(target=worker.run, daemon=True)
            thread.start()
        yield
        if worker:
            worker.stop_event.set()
            thread.join(timeout=10)

    app = FastAPI(title='Feedback Workspace',version='1.0.0',lifespan=lifespan)
    app.state.store, app.state.registry = store, registry

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        body = dict(code=exc.code,message=exc.message)
        if exc.details is not None: body['details'] = exc.details
        return JSONResponse(body,status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(dict(code='VALIDATION_ERROR',message='Dữ liệu yêu cầu không hợp lệ.',details=[dict(location=list(e['loc']),message=e['msg'],type=e['type']) for e in exc.errors()]),status_code=422)

    from starlette.exceptions import HTTPException
    @app.exception_handler(HTTPException)
    async def http_error(request,exc):
        return JSONResponse(dict(code='HTTP_ERROR',message=str(exc.detail)),status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request,exc):
        return JSONResponse(dict(code='INTERNAL_ERROR',message='Không thể hoàn tất yêu cầu. Kiểm tra trạng thái dịch vụ.'),status_code=500)

    prefix = '/api/v1'

    @app.get(prefix+'/health')
    def health():
        return dict(status='ok',worker=store.worker_health(),runtime=str(store.runtime),database_version=store.database_version())

    @app.get(prefix+'/profiles')
    def profiles():
        return [dict(p,model=registry.status(p['id'])) for p in PROFILES]

    @app.get(prefix+'/models')
    def models():
        return [dict(profile=p['id'],**registry.status(p['id'])) for p in PROFILES]

    @app.get(prefix+'/review-policy')
    def review_policy(profile:str):
        return resolve_policy_metadata(profile_for(profile)['schema_id'])

    @app.get(prefix+'/datasets')
    def datasets(): return store.datasets()

    @app.post(prefix+'/datasets',status_code=201)
    def create_dataset(body:DatasetInput,idempotency_key:str|None=Header(default=None)):
        return store.create_dataset(body.model_dump(exclude_none=True),idempotency_key)

    @app.get(prefix+'/datasets/{dataset_id}')
    def get_dataset(dataset_id:str): return store.dataset(dataset_id)

    @app.patch(prefix+'/datasets/{dataset_id}')
    def rename(dataset_id:str,body:NameInput): return store.rename(dataset_id,body.name)

    @app.delete(prefix+'/datasets/{dataset_id}',status_code=204)
    def delete(dataset_id:str):
        store.delete_dataset(dataset_id)
        return Response(status_code=204)

    @app.post(prefix+'/datasets/{dataset_id}/copy',status_code=201)
    def copy(dataset_id:str,body:CopyInput): return store.copy_dataset(dataset_id,body.model_dump())

    @app.post(prefix+'/datasets/{dataset_id}/items',status_code=201)
    def add_items(dataset_id:str,body:ItemsInput): return store.add_items(dataset_id,[i.model_dump() for i in body.items])

    @app.post(prefix+'/imports/preview')
    async def preview(file:UploadFile=File(...),delimiter:str|None=Form(default=None)):
        data = await file.read(5*1024*1024+1)
        return store.preview(data,delimiter)

    @app.post(prefix+'/analysis-runs',status_code=202)
    def run(body:RunInput,idempotency_key:str|None=Header(default=None)):
        dataset = store.dataset(body.dataset_id)
        return store.create_run(body.dataset_id,registry.status(dataset['profile']),idempotency_key,body.model_dump())

    @app.get(prefix+'/datasets/{dataset_id}/analysis-runs')
    def runs(dataset_id:str): return store.runs(dataset_id)

    @app.get(prefix+'/analysis-runs/{run_id}')
    def get_run(run_id:str): return store.run(run_id)

    @app.post(prefix+'/quick-analysis',status_code=202)
    def quick(body:QuickInput):
        from services.storage.db import check_text
        check_text(body.text); profile_for(body.profile)
        status = registry.status(body.profile)
        if not status.get('available'): raise DomainError('MODEL_UNAVAILABLE',status.get('reason') or 'Model chưa sẵn sàng.',409)
        dataset = store.create_dataset(dict(name='Thử một câu',profile=body.profile,items=[dict(text=body.text, metadata={'_temporary_source': 'quick-analysis-v1'})]),temporary=True)
        try:
            run = store.create_run(dataset['id'],status)
        except BaseException:
            store.delete_dataset(dataset['id']); raise
        return dict(job_id=run['job_id'],run_id=run['id'])

    @app.post(prefix+'/quick-analysis/{job_id}/explanation')
    async def quick_explanation(job_id: str, body: ExplanationInput, request: Request):
        check_origin(request)
        raise DomainError('EXPLANATION_DISABLED', 'Dịch vụ diễn giải LLM đã được loại bỏ.', 410)

    @app.post(prefix+'/quick-analysis/{job_id}/attribution')
    def create_attribution(job_id: str, body: AttributionRequestInput, request: Request, response: Response, idempotency_key: str | None = Header(default=None)):
        check_origin(request)
        res = store.create_attribution_job(
            job_id,
            body.source_prediction_id,
            body.target.model_dump(exclude_none=True),
            idempotency_key=idempotency_key,
            execution_resolver=registry.execution_identity,
        )
        if res.get('status') == 'completed':
            response.status_code = 200
        else:
            response.status_code = 202
        return res

    @app.get(prefix+'/attributions/{attribution_id}')
    def get_attribution(attribution_id: str):
        return store.get_attribution(attribution_id, execution_resolver=registry.execution_identity)

    @app.post(prefix+'/attributions/{attribution_id}/cancel')
    def cancel_attribution(attribution_id: str, request: Request):
        check_origin(request)
        return store.cancel_attribution(attribution_id)

    @app.get(prefix+'/jobs/{job_id}')
    def job(job_id:str): return store.job(job_id)

    @app.post(prefix+'/jobs/{job_id}/cancel')
    def cancel(job_id:str): return store.cancel(job_id)

    @app.post(prefix+'/jobs/{job_id}/retry')
    def retry(job_id:str):
        j = store.job(job_id); r = store.run(j['run_id']); d = store.dataset(r['dataset_id'])
        if j.get('kind') == 'sensitivity':
            return store.retry(job_id, execution_resolver=registry.execution_identity)
        return store.retry(job_id,registry.status(d['profile']))

    def query_filters(request):
        values = dict(request.query_params)
        values.pop('page',None); values.pop('page_size',None)
        values.pop('scope_token', None); values.pop('expected_run_id', None)
        try: return Filters.model_validate(values).model_dump(exclude_none=True)
        except Exception: raise DomainError('INVALID_FILTER','Bộ lọc không hợp lệ.',422)

    @app.get(prefix+'/datasets/{dataset_id}/items')
    def items(dataset_id:str,request:Request,page:int=1,page_size:int=25):
        if page < 1 or page_size < 1 or page_size > 500: raise DomainError('INVALID_PAGINATION','Trang không hợp lệ.',422)
        filters = query_filters(request)
        from services.demo_scope import scoped_response
        return scoped_response(store, dataset_id, filters, page=page, page_size=page_size,
                               expected_token=request.query_params.get('scope_token'),
                               expected_run_id=request.query_params.get('expected_run_id'))

    @app.get(prefix+'/datasets/{dataset_id}/summary')
    def summary(dataset_id:str,request:Request):
        from services.demo_scope import scoped_response
        return scoped_response(store, dataset_id, query_filters(request))

    @app.get(prefix+'/datasets/{dataset_id}/network')
    def dataset_network(dataset_id: str, request: Request):
        from services.network_jobs import request_network
        return request_network(store, dataset_id, query_filters(request))

    @app.get(prefix+'/networks/{network_id}/evidence')
    def network_evidence(network_id: str, selection_type: str, selection_id: str, page: int=1, page_size: int=10):
        if page < 1 or page_size < 1 or page_size > 500:
            raise DomainError('INVALID_PAGINATION','Trang không hợp lệ.',422)
        from services.network_jobs import evidence
        return evidence(store,network_id,selection_type,selection_id,page,page_size)

    @app.get(prefix+'/items/{item_id}')
    def item(item_id:str,run_id:str|None=None): return store.item(item_id,run_id)

    @app.patch(prefix+'/items/{item_id}/text')
    def edit(item_id:str,body:EditInput): return store.edit_text(item_id,body.text,body.expected_revision)

    @app.get(prefix+'/items/{item_id}/revisions')
    def revisions(item_id:str): return store.history(item_id,'revisions')

    @app.put(prefix+'/items/{item_id}/review')
    def review(item_id:str,body:ReviewInput): return store.review(item_id,body.model_dump(exclude_unset=True))

    @app.get(prefix+'/items/{item_id}/reviews')
    def reviews(item_id:str): return store.history(item_id,'reviews')

    @app.post(prefix+'/items/{item_id}/reviews/restore')
    def restore(item_id:str,body:RestoreInput): return store.review(item_id,body.model_dump(),restore=True)

    @app.post(prefix+'/items/{item_id}/sensitivity-experiments',status_code=202)
    def create_sensitivity_experiment(item_id:str,body:SensitivityExperimentInput,idempotency_key:str|None=Header(default=None)):
        if idempotency_key is None or not idempotency_key.strip():
            raise RequestValidationError([
                {
                    'type': 'missing' if idempotency_key is None else 'string_too_short',
                    'loc': ('header', 'idempotency-key'),
                    'msg': 'Idempotency-Key header is required.',
                    'input': idempotency_key,
                }
            ])
        return store.create_sensitivity_experiment(
            item_id,
            body.model_dump(),
            idempotency_key,
            execution_resolver=registry.execution_identity,
        )

    @app.get(prefix+'/sensitivity-experiments/{experiment_id}')
    def get_sensitivity_experiment(experiment_id:str):
        return store.get_sensitivity_experiment(
            experiment_id,
            execution_resolver=registry.execution_identity,
        )

    @app.post(prefix+'/datasets/{dataset_id}/exports',status_code=201)
    def export(dataset_id:str,body:dict[str,Any]):
        try:
            parsed = ExportInput.model_validate(body)
        except ValidationError as exc:
            errors = exc.errors()
            if any(e.get('type') == 'extra_forbidden' or (e.get('loc') and e['loc'][0] == 'scope') for e in errors):
                raise RequestValidationError(errors)
            raise DomainError('INVALID_FILTER', 'Bộ lọc không hợp lệ.', 422)
        filters = parsed.model_dump(exclude_none=True)
        scope = filters.pop('scope')
        if scope == 'all': filters = {k:v for k,v in filters.items() if k in ('run_id','label_source')}
        return store.export(dataset_id,filters)

    @app.get(prefix+'/exports/{export_id}')
    def download(export_id:str):
        return Response(store.export_bytes(export_id),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="feedback-{export_id}.csv"'})

    @app.get(prefix+'/research/summary')
    def research():
        from services.research import get_research_summary
        return get_research_summary()

    # API routes precede SPA fallback; an unknown API path must remain a JSON 404.
    @app.get('/{path:path}',include_in_schema=False)
    def spa(path:str):
        if path.startswith('api/') or path == 'api': raise DomainError('NOT_FOUND','Không tìm thấy API.',404)
        dist = ROOT / 'apps/web/dist'
        target = (dist/path).resolve()
        if target.is_relative_to(dist.resolve()) and target.is_file(): return FileResponse(target)
        index = dist/'index.html'
        if index.exists(): return FileResponse(index)
        raise DomainError('FRONTEND_NOT_BUILT','Chạy npm run build trong apps/web để mở giao diện.',404)

    return app


# Production always uses the real registry; test doubles are passed to create_app.
app = create_app()
