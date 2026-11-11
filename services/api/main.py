import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

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


def create_app(runtime_dir=None, registry=None, start_worker=False):
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
        dataset = store.create_dataset(dict(name='Thử một câu',profile=body.profile,items=[dict(text=body.text)]),temporary=True)
        try:
            run = store.create_run(dataset['id'],status)
        except BaseException:
            store.delete_dataset(dataset['id']); raise
        return dict(job_id=run['job_id'],run_id=run['id'])

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
        try: return Filters.model_validate(values).model_dump(exclude_none=True)
        except Exception: raise DomainError('INVALID_FILTER','Bộ lọc không hợp lệ.',422)

    @app.get(prefix+'/datasets/{dataset_id}/items')
    def items(dataset_id:str,request:Request,page:int=1,page_size:int=25):
        if page < 1 or page_size < 1 or page_size > 500: raise DomainError('INVALID_PAGINATION','Trang không hợp lệ.',422)
        filters = query_filters(request)
        return store.items_page(dataset_id,filters,page,page_size)

    @app.get(prefix+'/datasets/{dataset_id}/summary')
    def summary(dataset_id:str,request:Request): return store.summary(dataset_id,query_filters(request))

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
