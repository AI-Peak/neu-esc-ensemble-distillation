import csv
import io
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import DomainError, Store, profile_for
from services.worker import Worker


class Registry:
    def __init__(self):
        self.available = True
        self.fail = False
        self.version = 'v1'
        self.calls = []
        self.hook = None
        self.bad = None

    def status(self,profile):
        return dict(available=self.available,reason=None if self.available else 'Artifact missing',model_id='test-'+profile,model_version=self.version,schema_id=profile_for(profile)['schema_id'])

    def predict(self,profile,items):
        self.calls.append([i['item_id'] for i in items])
        if self.hook: self.hook()
        if self.fail: raise RuntimeError('PRIVATE INPUT MUST NOT BE PERSISTED')
        result=[]
        for i in items:
            value=dict(item_id=i['item_id'],revision_id=i['revision_id'],model_id='test-'+profile,model_version=self.version,schema_id=profile_for(profile)['schema_id'],token_count_before_truncation=4,truncated=False,warnings=[],duration_ms=1)
            for task in ('sentiment','topic'):
                count=len(profile_for(profile)[task]); scores=[.1/(count-1)]*count; scores[1]=.9
                value[task]=dict(label_id=1,scores=scores)
            if self.bad: self.bad(value)
            result.append(value)
        return list(reversed(result)) # The worker must join by IDs, never output order.


@pytest.fixture
def env(tmp_path):
    registry=Registry()
    app=create_app(tmp_path,registry)
    with TestClient(app) as client:
        yield client,app.state.store,registry,Worker(tmp_path,registry,batch_size=1)


def dataset(client,texts=None,**kwargs):
    response=client.post('/api/v1/datasets',json=dict(name='Góp ý',profile='uit',items=[dict(text=t) for t in (texts or ['Tốt','Cần cải thiện'])],**kwargs))
    assert response.status_code==201,response.text
    return response.json()


def run(client,d):
    response=client.post('/api/v1/analysis-runs',json=dict(dataset_id=d['id']))
    assert response.status_code==202,response.text
    return response.json()


def drain(worker):
    for _ in range(510):
        if not worker.run_once(): return
    raise AssertionError('Worker did not drain')


def items(client,d,**params):
    response=client.get(f"/api/v1/datasets/{d['id']}/items",params=params)
    assert response.status_code==200,response.text
    return response.json()['items']


def test_durable_api_restart_missing_model_and_immutable_profile(env,tmp_path):
    c,s,r,w=env
    d=dataset(c)
    assert c.get('/api/v1/profiles').json()[1]['sentiment'][0]['key']=='negative'
    assert c.patch(f"/api/v1/datasets/{d['id']}",json={'profile':'neu'}).status_code==422
    r.available=False
    response=c.post('/api/v1/analysis-runs',json={'dataset_id':d['id']})
    assert response.status_code==409 and response.json()['code']=='MODEL_UNAVAILABLE'
    assert c.get('/api/v1/models').json()[0]['available'] is False
    with TestClient(create_app(tmp_path,r)) as restarted:
        assert restarted.get('/api/v1/datasets').json()[0]['item_count']==2
    assert c.get('/api/v1/health').json()['worker']['alive'] is False
    w.run_once()
    assert c.get('/api/v1/health').json()['worker']['alive'] is True


def test_csv_bom_quotes_newline_validation_reference_and_metadata(env):
    c,s,r,w=env
    content='comment;gold;department\r\n"Phòng học\nquá nóng";bad;Đào tạo\r\n"=SUM(A1)";good;Kế toán\r\n;bad;Khoa\r\n"=SUM(A1)";good;Kế toán\r\n'.encode('utf-8-sig')
    preview=c.post('/api/v1/imports/preview',files={'file':('x.csv',content,'text/csv')}).json()
    assert preview['delimiter']==';' and preview['total_rows']==4
    assert any(x['code']=='DUPLICATE' for x in preview['issues'])
    body=dict(name='CSV',profile='uit',preview_id=preview['preview_id'],text_column='comment',reference=dict(source='Người cung cấp',sentiment_column='gold',sentiment_map={'bad':0,'good':2}))
    assert c.post('/api/v1/datasets',json=body).json()['code']=='INVALID_ROWS'
    body['skip_invalid']=True
    response=c.post('/api/v1/datasets',json=body)
    assert response.status_code==201,response.text
    d=response.json(); rows=items(c,d)
    assert [i['source_row'] for i in rows]==[1,2,4]
    assert rows[0]['text']=='Phòng học\nquá nóng'
    assert rows[0]['metadata']['department']=='Đào tạo'
    assert rows[0]['reference']['sentiment']['label_id']==0
    assert rows[0]['effective']['sentiment'] is None # Reference is never operational fallback.
    assert d['skipped_count']==1
    body['reference']['sentiment_map']['bad']=3
    assert c.post('/api/v1/datasets',json=body).json()['code']=='INVALID_REFERENCE'
    assert c.post('/api/v1/imports/preview',files={'file':('bad.csv',b'text\n\xff')}).status_code==422


def test_csv_selected_column_structural_errors_and_limits(env):
    c,s,r,w=env
    p=c.post('/api/v1/imports/preview',files={'file':('x.csv',b'other,text\na,\nb,valid,EXTRA\nc,ok\n')}).json()
    body=dict(name='CSV',profile='uit',preview_id=p['preview_id'],text_column='text')
    response=c.post('/api/v1/datasets',json=body)
    assert response.status_code==422 and len(response.json()['details'])==2
    body['skip_invalid']=True
    d=c.post('/api/v1/datasets',json=body).json()
    assert d['item_count']==1 and items(c,d)[0]['source_row']==3
    assert c.post('/api/v1/imports/preview',files={'file':('huge.csv',b'x'*(5*1024*1024+1))}).status_code==413
    assert c.post('/api/v1/datasets',json=dict(name='x',profile='uit',items=[dict(text='x')]*501)).status_code==422
    assert c.post('/api/v1/datasets',json=dict(name='x',profile='uit',items=[dict(text='x'*5001)])).status_code==422


def test_analysis_review_independent_optimistic_undo_and_snapshot_export(env):
    c,s,r,w=env
    d=dataset(c,['=HYPERLINK("x")','Bình thường'])
    first=run(c,d); drain(w)
    a=items(c,d)[0]
    assert a['prediction']['item_id']==a['id']
    url=f"/api/v1/items/{a['id']}/review"
    body=dict(task='sentiment',status='corrected',label_id=0,note='  =danger',expected_revision=1,expected_review_revision=0)
    rev=c.put(url,json=body).json()
    assert rev['revision']==1 and rev['source_prediction_id']==a['prediction']['id']
    assert c.put(url,json=body).status_code==409
    assert items(c,d)[0]['reviews']['topic'] is None
    summary=c.get(f"/api/v1/datasets/{d['id']}/summary",params={'sentiment':0}).json()
    assert summary['total']==1 and summary['partial_review']==1 and summary['denominator']['cross']==1
    ai=c.get(f"/api/v1/datasets/{d['id']}/summary",params={'sentiment':0,'label_source':'ai'}).json()
    assert ai['total']==0
    response=c.post(f"/api/v1/datasets/{d['id']}/exports",json={'sentiment':0})
    export=response.json(); before=c.get(export['url']).content
    assert before.startswith(b'\xef\xbb\xbf')
    parsed=list(csv.DictReader(io.StringIO(before.decode('utf-8-sig'))))
    assert len(parsed)==1 and parsed[0]['text'].startswith("'=") and parsed[0]['review_sentiment_note'].startswith("'  =")
    body.update(label_id=2,expected_review_revision=1)
    assert c.put(url,json=body).json()['revision']==2
    restored=c.post(f"/api/v1/items/{a['id']}/reviews/restore",json=dict(task='sentiment',review_revision=1,expected_revision=1,expected_review_revision=2)).json()
    assert restored['revision']==3 and restored['label_id']==0
    assert c.get(export['url']).content==before
    assert len(c.get(f"/api/v1/items/{a['id']}/reviews").json())==3
    ai_export=c.post(f"/api/v1/datasets/{d['id']}/exports",json={'label_source':'ai'}).json()
    rows=list(csv.DictReader(io.StringIO(c.get(ai_export['url']).content.decode('utf-8-sig'))))
    assert rows[0]['selected_sentiment']=='1' and rows[0]['effective_sentiment']=='0'
    confirm=dict(task='topic',status='confirmed',label_id=0,note='',expected_revision=1,expected_review_revision=0)
    assert c.put(url,json=confirm).status_code==409
    confirm['label_id']=1
    assert c.put(url,json=confirm).status_code==200


def test_runs_pin_text_revisions_no_fallback_and_copy_schema(env):
    c,s,r,w=env
    d=dataset(c); first=run(c,d); drain(w)
    a=items(c,d)[0]
    edited=c.patch(f"/api/v1/items/{a['id']}/text",json={'text':'Nội dung mới','expected_revision':1}).json()
    assert edited['revision']==2 and edited['prediction'] is None and edited['reviews']['sentiment'] is None
    assert c.patch(f"/api/v1/items/{a['id']}/text",json={'text':'Conflict','expected_revision':1}).status_code==409
    old=c.get(f"/api/v1/items/{a['id']}",params={'run_id':first['id']}).json()
    assert old['stale'] and old['text']=='Tốt' and old['prediction']
    assert len(c.get(f"/api/v1/items/{a['id']}/revisions").json())==2
    second=run(c,d)
    assert all(i['prediction'] is None for i in items(c,d))
    w.run_once()
    assert sum(bool(i['prediction']) for i in items(c,d))==1
    copied=c.post(f"/api/v1/datasets/{d['id']}/copy",json=dict(name='NEU copy',profile='neu')).json()
    assert copied['schema_id']=='neu-v1'
    assert all(not i['prediction'] and not i['reference'] for i in items(c,copied))


def test_idempotency_cancel_and_retry_incomplete_only(env):
    c,s,r,w=env
    body=dict(name='Idempotent',profile='uit',items=[dict(text='One'),dict(text='Two')])
    headers={'Idempotency-Key':'import-key'}
    d=c.post('/api/v1/datasets',json=body,headers=headers).json()
    assert c.post('/api/v1/datasets',json=body,headers=headers).json()['id']==d['id']
    body['name']='Different'
    assert c.post('/api/v1/datasets',json=body,headers=headers).status_code==409
    body=dict(dataset_id=d['id']); headers={'Idempotency-Key':'run-key'}
    first=c.post('/api/v1/analysis-runs',json=body,headers=headers).json()
    assert c.post('/api/v1/analysis-runs',json=body,headers=headers).json()['id']==first['id']
    w.run_once()
    c.post(f"/api/v1/jobs/{first['job_id']}/cancel")
    drain(w)
    job=c.get(f"/api/v1/jobs/{first['job_id']}").json()
    assert job['status']=='cancelled' and job['completed']==1
    assert c.post(f"/api/v1/jobs/{job['id']}/retry").status_code==200
    drain(w)
    assert c.get(f"/api/v1/jobs/{job['id']}").json()['completed']==2
    assert len([x for call in r.calls for x in call])==2
    with s.connect() as db: assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]==2


def test_errors_retry_and_model_fencing(env):
    c,s,r,w=env
    d=dataset(c); first=run(c,d); r.fail=True; drain(w)
    job=c.get(f"/api/v1/jobs/{first['job_id']}").json()
    assert job['status']=='completed_with_errors' and job['failed']==2 and job['completed']==0
    assert 'PRIVATE' not in json.dumps(job)
    assert len(job['errors'])==2
    r.version='v2'
    assert c.post(f"/api/v1/jobs/{job['id']}/retry").status_code==409
    r.version='v1';r.fail=False
    assert c.post(f"/api/v1/jobs/{job['id']}/retry").status_code==200
    drain(w)
    assert c.get(f"/api/v1/jobs/{job['id']}").json()['status']=='completed'


def test_lease_recovery_and_stale_worker_cannot_commit(env):
    c,s,r,w=env
    d=dataset(c); first=run(c,d)
    def steal():
        with s.tx() as db:
            db.execute('UPDATE jobs SET lease_expires_at=? WHERE id=?',(time.time()-1,first['job_id']))
        s.cleanup()
        assert c.post(f"/api/v1/jobs/{first['job_id']}/retry").status_code==200
    r.hook=steal
    w.run_once()
    assert not any(i['prediction'] for i in items(c,d))
    r.hook=None
    restarted=Worker(s.runtime,r,batch_size=2)
    drain(restarted)
    assert c.get(f"/api/v1/jobs/{first['job_id']}").json()['completed']==2
    with s.connect() as db: assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]==2


def test_quick_priority_cleanup_terminal_and_lock(env):
    c,s,r,w=env
    d=dataset(c); bulk=run(c,d)
    quick=c.post('/api/v1/quick-analysis',json=dict(profile='uit',text='Câu tạm')).json()
    w.run_once()
    job=c.get(f"/api/v1/jobs/{quick['job_id']}").json()
    assert job['status']=='completed' and job['result']['prediction']
    assert c.get(f"/api/v1/jobs/{bulk['job_id']}").json()['completed']==0
    assert len(c.get('/api/v1/datasets').json())==1
    with w.process_lock():
        with pytest.raises(RuntimeError):
            with Worker(s.runtime,r).process_lock(): pass
    with s.tx() as db: db.execute('UPDATE datasets SET expires_at=? WHERE temporary=1',(time.time()-1,))
    s.cleanup()
    assert c.get(f"/api/v1/jobs/{quick['job_id']}").status_code==404
    assert c.get(f"/api/v1/datasets/{d['id']}").status_code==200


@pytest.mark.parametrize('bad',[lambda x:x.update(model_version='changed'),lambda x:x.update(item_id='wrong'),lambda x:x['sentiment'].update(scores=[float('nan')]*3),lambda x:x['topic'].update(label_id=99)])
def test_invalid_registry_output_never_commits(env,bad):
    c,s,r,w=env
    d=dataset(c); first=run(c,d);r.bad=bad;drain(w)
    job=c.get(f"/api/v1/jobs/{first['job_id']}").json()
    assert job['failed']==2 and job['completed']==0


def test_delete_cascades_exports_runs_and_revisions(env):
    c,s,r,w=env
    d=dataset(c); first=run(c,d);drain(w)
    export=c.post(f"/api/v1/datasets/{d['id']}/exports",json={}).json()
    assert c.delete(f"/api/v1/datasets/{d['id']}").status_code==204
    assert c.get(export['url']).status_code==404
    assert c.get(f"/api/v1/jobs/{first['job_id']}").status_code==404
    with s.connect() as db:
        for table in ('datasets','items','revisions','runs','run_items','predictions','reviews','exports','jobs'):
            assert db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0


def test_concurrent_database_initialization(tmp_path):
    with ThreadPoolExecutor(max_workers=4) as pool:
        stores=list(pool.map(lambda _:Store(tmp_path),range(4)))
    assert stores[0].database_version()==2
    with stores[0].connect() as db:
        versions=[row[0] for row in db.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall()]
        assert versions==[1,2]
        tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {'sensitivity_experiments','sensitivity_rate_limits'}.issubset(tables)


def test_skipped_source_rows_append_and_export_run_lineage(env):
    c,s,r,w=env
    p=c.post('/api/v1/imports/preview',files={'file':('x.csv',b'text,meta\na,x\n,y\nc,z\n')}).json()
    d=c.post('/api/v1/datasets',json=dict(name='Rows',profile='uit',preview_id=p['preview_id'],text_column='text',skip_invalid=True)).json()
    assert c.post(f"/api/v1/datasets/{d['id']}/items",json={'items':[{'text':'new'}]}).status_code==201
    assert [i['source_row'] for i in items(c,d)]==[1,3,4]
    first=run(c,d); w.run_once()
    export=c.post(f"/api/v1/datasets/{d['id']}/exports",json={}).json()
    rows=list(csv.DictReader(io.StringIO(c.get(export['url']).content.decode('utf-8-sig'))))
    assert {row['selected_run_id'] for row in rows}=={first['id']}
    assert rows[0]['run_id']==first['id'] and rows[0]['model_version']=='v1'
    assert all(row['run_id']==row['model_version']=='' for row in rows[1:])
    assert [row['prediction_status'] for row in rows]==['processed','unprocessed','unprocessed']
    with s.connect() as db:
        assert db.execute('SELECT run_id FROM exports WHERE id=?',(export['id'],)).fetchone()[0]==first['id']


def test_restore_cannot_cross_input_revision_even_when_review_numbers_match(env):
    c,s,r,w=env
    d=dataset(c); a=items(c,d)[0]
    url=f"/api/v1/items/{a['id']}/review"
    c.put(url,json=dict(task='sentiment',status='corrected',label_id=0,expected_revision=1,expected_review_revision=0))
    c.patch(f"/api/v1/items/{a['id']}/text",json=dict(text='Edited',expected_revision=1))
    c.put(url,json=dict(task='sentiment',status='corrected',label_id=2,expected_revision=2,expected_review_revision=0))
    response=c.post(f"/api/v1/items/{a['id']}/reviews/restore",json=dict(task='sentiment',review_revision=1,revision_id=a['revision_id'],expected_revision=2,expected_review_revision=1))
    assert response.status_code==422 and response.json()['code']=='INVALID_RESTORE'
    assert items(c,d)[0]['effective']['sentiment']==2


@pytest.mark.parametrize('outcome',['cancel','failure'])
def test_quick_failed_and_cancelled_payloads_expire(env,outcome):
    c,s,r,w=env
    quick=c.post('/api/v1/quick-analysis',json=dict(profile='uit',text='Private quick text')).json()
    if outcome=='cancel': c.post(f"/api/v1/jobs/{quick['job_id']}/cancel")
    else: r.fail=True; drain(w)
    with s.connect() as db:
        row=db.execute('SELECT expires_at FROM datasets WHERE temporary=1').fetchone()
        assert time.time()+895 < row['expires_at'] < time.time()+905
    with s.tx() as db: db.execute('UPDATE datasets SET expires_at=? WHERE temporary=1',(time.time()-1,))
    Store(s.runtime) # Startup cleanup must remove all private revisions/jobs as well.
    assert c.get(f"/api/v1/jobs/{quick['job_id']}").status_code==404
    with s.connect() as db: assert db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0]==0


def test_heartbeat_keeps_slow_inference_lease_and_quick_preempts_between_batches(env):
    c,s,r,w=env
    w.lease_seconds=.2
    r.hook=lambda:time.sleep(.45)
    d=dataset(c); bulk=run(c,d)
    w.run_once()
    assert c.get(f"/api/v1/jobs/{bulk['job_id']}").json()['completed']==1
    r.hook=None
    quick=c.post('/api/v1/quick-analysis',json=dict(profile='uit',text='Priority')).json()
    w.run_once()
    assert c.get(f"/api/v1/jobs/{quick['job_id']}").json()['status']=='completed'
    assert c.get(f"/api/v1/jobs/{bulk['job_id']}").json()['completed']==1
    drain(w)
    assert c.get(f"/api/v1/jobs/{bulk['job_id']}").json()['completed']==2


def test_get_job_marks_dead_worker_interrupted_without_api_restart(env):
    c,s,r,w=env
    d=dataset(c); first=run(c,d)
    assert w.claim()
    with s.tx() as db: db.execute('UPDATE jobs SET lease_expires_at=? WHERE id=?',(time.time()-1,first['job_id']))
    assert c.get(f"/api/v1/jobs/{first['job_id']}").json()['status']=='interrupted'


def test_confirmation_note_preserves_explicit_source_from_another_displayed_run(env):
    c,s,r,w=env
    d=dataset(c); first=run(c,d); drain(w)
    a=items(c,d)[0]; source=a['prediction']['id']
    url=f"/api/v1/items/{a['id']}/review"
    body=dict(task='sentiment',status='confirmed',label_id=1,note='original',
              expected_revision=1,expected_review_revision=0,run_id=first['id'])
    assert c.put(url,json=body).status_code==200
    def different_prediction(value):
        value['sentiment']=dict(label_id=2,scores=[.05,.05,.9])
    r.bad=different_prediction
    second=run(c,d); drain(w)
    displayed=items(c,d)[0]['prediction']
    body.update(run_id=second['id'],source_prediction_id=source,note='note only',expected_review_revision=1)
    response=c.put(url,json=body)
    assert response.status_code==200,response.text
    assert response.json()['label_id']==1 and response.json()['source_prediction_id']==source
    assert c.put(url,json=body).json()['code']=='REVIEW_CONFLICT'
    body.update(label_id=2,source_prediction_id=displayed['id'],expected_review_revision=2)
    assert c.put(url,json=body).json()['source_prediction_id']==displayed['id']
    history=c.get(f"/api/v1/items/{a['id']}/reviews").json()
    assert [x['label_id'] for x in history]==[1,1,2]
    assert c.get(f"/api/v1/items/{a['id']}",params={'run_id':first['id']}).json()['prediction']['sentiment']['label_id']==1


@pytest.mark.parametrize('invalid_source',['missing','other_item','old_revision','wrong_label','wrong_schema'])
def test_confirmation_source_must_match_item_revision_schema_and_task_label(env,invalid_source):
    c,s,r,w=env
    d=dataset(c); first=run(c,d); drain(w)
    a,b=items(c,d)
    source=a['prediction']['id']; label=1; revision=1
    if invalid_source=='missing': source='not-a-prediction'
    if invalid_source=='other_item': source=b['prediction']['id']
    if invalid_source=='old_revision':
        c.patch(f"/api/v1/items/{a['id']}/text",json=dict(text='new revision',expected_revision=1))
        revision=2
    if invalid_source=='wrong_label': label=2
    if invalid_source=='wrong_schema':
        with s.tx() as db:
            payload=json.loads(db.execute('SELECT payload FROM predictions WHERE id=?',(source,)).fetchone()[0])
            payload['schema_id']='wrong-schema'
            db.execute('UPDATE predictions SET payload=? WHERE id=?',(json.dumps(payload),source))
    response=c.put(f"/api/v1/items/{a['id']}/review",json=dict(task='sentiment',status='confirmed',label_id=label,
        source_prediction_id=source,expected_revision=revision,expected_review_revision=0))
    assert response.status_code==409 and response.json()['code']=='CONFIRM_REQUIRES_PREDICTION'
    assert c.get(f"/api/v1/items/{a['id']}/reviews").json()==[]


@pytest.mark.parametrize('status',['corrected','unreviewed'])
def test_saved_manual_review_source_can_be_preserved_or_deliberately_cleared(env,status):
    c,s,r,w=env
    d=dataset(c); first=run(c,d); drain(w)
    a=items(c,d)[0]; source=a['prediction']['id']
    second=run(c,d); drain(w)
    body=dict(task='sentiment',status=status,label_id=0,source_prediction_id=source,
              expected_revision=1,expected_review_revision=0,run_id=second['id'],note='retained source')
    url=f"/api/v1/items/{a['id']}/review"
    saved=c.put(url,json=body)
    assert saved.status_code==200 and saved.json()['source_prediction_id']==source
    body.update(source_prediction_id=None,expected_review_revision=1)
    cleared=c.put(url,json=body)
    assert cleared.status_code==200 and cleared.json()['source_prediction_id'] is None


def test_null_confirmation_source_retains_selected_prediction_fallback(env):
    c,s,r,w=env
    d=dataset(c); run(c,d); drain(w)
    a=items(c,d)[0]
    response=c.put(f"/api/v1/items/{a['id']}/review",json=dict(task='topic',status='confirmed',label_id=1,
        source_prediction_id=None,expected_revision=1,expected_review_revision=0))
    assert response.status_code==200 and response.json()['source_prediction_id']==a['prediction']['id']


def test_export_current_and_historical_revisions_have_real_prediction_provenance(env):
    c,s,r,w=env
    d=dataset(c,['old text','still analyzed']); first=run(c,d); drain(w)
    original=items(c,d)
    c.patch(f"/api/v1/items/{original[0]['id']}/text",json=dict(text='=new text',expected_revision=1))
    c.post(f"/api/v1/datasets/{d['id']}/items",json=dict(items=[dict(text='appended')]))
    def exported(filters):
        response=c.post(f"/api/v1/datasets/{d['id']}/exports",json=filters).json()
        content=c.get(response['url']).content
        assert content.startswith(b'\xef\xbb\xbf')
        return response,content,list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    snapshot,content,current=exported({})
    assert [row['prediction_status'] for row in current]==['unprocessed','processed','unprocessed']
    assert {row['selected_run_id'] for row in current}=={first['id']}
    for row in (current[0],current[2]):
        assert row['run_id']==row['model_id']==row['model_version']==row['prediction_id']==''
        assert row['ai_sentiment']==''
    assert current[0]['text']=="'=new text" and current[0]['revision']=='2'
    assert current[1]['run_id']==first['id'] and current[1]['model_version']=='v1'
    _,_,historic=exported(dict(run_id=first['id']))
    assert len(historic)==2 and historic[0]['text']=='old text' and historic[0]['revision']=='1'
    assert all(row['prediction_status']=='processed' and row['run_id']==first['id'] for row in historic)
    second=run(c,d); w.run_once()
    r.fail=True; w.run_once()
    _,_,partial=exported({})
    assert [row['prediction_status'] for row in partial]==['processed','failed','unprocessed']
    assert {row['selected_run_id'] for row in partial}=={second['id']}
    assert partial[1]['error'] and partial[1]['run_id']==partial[1]['model_id']==''
    assert partial[2]['error']=='' and partial[2]['run_id']==''
    assert c.get(snapshot['url']).content==content
