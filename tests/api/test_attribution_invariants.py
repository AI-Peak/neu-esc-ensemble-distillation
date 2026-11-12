"""Software games only: provenance, fencing, bounded jobs and schema regressions."""
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.storage.db import Store
from services.worker import Worker
from tests.support import TestOnlyRegistry


@pytest.fixture
def ctx(tmp_path):
    registry = TestOnlyRegistry()
    app = create_app(tmp_path,registry)
    return TestClient(app), Worker(tmp_path,registry,batch_size=2), registry


def source(ctx, profile='neu', text='Wifi thư viện hơi chậm nhưng nhân viên hỗ trợ tốt.'):
    client, worker, registry = ctx
    job = client.post('/api/v1/quick-analysis',json=dict(profile=profile,text=text)).json()['job_id']
    worker.run_once()
    return job,client.get('/api/v1/jobs/'+job).json()['result']['prediction']['id']


def create(ctx, src, target=None, key=None):
    return ctx[0].post('/api/v1/quick-analysis/'+src[0]+'/attribution',
        json=dict(source_prediction_id=src[1],target=target or dict(kind='polarity_margin')),
        headers={'Idempotency-Key':key or str(uuid.uuid4())})


def drain(ctx, attr_id):
    for _ in range(120):
        value=ctx[1].store.get_attribution(attr_id)
        if value['status'] not in ('queued','running'):
            return value
        ctx[1].run_once()
    raise AssertionError('Attribution did not terminate')


@pytest.mark.parametrize('profile,count',[('neu',4),('uit',3)])
def test_every_schema_target(ctx,profile,count):
    src=source(ctx,profile)
    for label in range(count):
        res=create(ctx,src,dict(kind='label_score',label_id=label))
        assert res.status_code==202,res.text
        value=drain(ctx,res.json()['attribution_id'])
        assert value['status']=='completed',value
        assert value['method']['target']==dict(kind='label_score',label_id=label)


@pytest.mark.parametrize('label',[-1,4,True,1.0,None])
def test_invalid_labels_rejected(ctx,label):
    assert create(ctx,source(ctx),dict(kind='label_score',label_id=label)).status_code==422


@pytest.mark.parametrize('key',[None,'','bad-key'])
def test_uuid_required(ctx,key):
    src=source(ctx)
    res=ctx[0].post('/api/v1/quick-analysis/'+src[0]+'/attribution',
        json=dict(source_prediction_id=src[1],target=dict(kind='polarity_margin')),
        headers={} if key is None else {'Idempotency-Key':key})
    assert res.status_code==422


def test_cache_handle_idempotency_and_cancel_isolation(ctx):
    src=source(ctx); a=create(ctx,src).json()['attribution_id']
    assert drain(ctx,a)['status']=='completed'
    key=str(uuid.uuid4());b=create(ctx,src,key=key)
    assert b.status_code==200 and b.json()['attribution_id']!=a
    assert create(ctx,src,key=key).json()['attribution_id']==b.json()['attribution_id']
    assert create(ctx,src,dict(kind='label_score',label_id=0),key).status_code==409
    assert ctx[0].post('/api/v1/attributions/'+a+'/cancel').json()['status']=='completed'
    assert ctx[0].get('/api/v1/attributions/'+b.json()['attribution_id']).json()['status']=='completed'
    c=create(ctx,src,dict(kind='label_score',label_id=0)).json()['attribution_id']
    d=create(ctx,src,dict(kind='label_score',label_id=0)).json()['attribution_id']
    assert c!=d
    assert ctx[0].post('/api/v1/attributions/'+c+'/cancel').json()['status']=='cancelled'
    assert drain(ctx,d)['status']=='completed'


@pytest.mark.parametrize('field',['model_version','manifest_sha256','preprocessing_sha256'])
def test_bundle_changes_before_and_between_batches(ctx,field):
    src=source(ctx);a=create(ctx,src).json()['attribution_id']
    ctx[1].run_once()
    setattr(ctx[2],field,'changed-version' if field=='model_version' else 'b'*64)
    value=drain(ctx,a)
    assert value['status']=='failed' and value['error']['code']=='MODEL_IDENTITY_CHANGED'
    assert create(ctx,src).status_code==409
    assert ctx[0].get('/api/v1/jobs/'+src[0]).json()['status']=='completed'


def test_vectors_mismatch_cannot_hide_behind_residual(ctx):
    src=source(ctx);a=create(ctx,src).json()['attribution_id']
    original=ctx[2].get_loaded_bundle
    def wrong(profile):
        model,tok,pre,identity,manifest=original(profile)
        class Wrong:
            def __call__(self,input_ids,attention_mask):
                import torch
                sent,topic=model(input_ids,attention_mask)
                return sent,torch.roll(topic,1,dims=1)
        return Wrong(),tok,pre,identity,manifest
    ctx[2].get_loaded_bundle=wrong
    value=drain(ctx,a)
    assert value['status']=='failed' and value['error']['code']=='PREDICTION_MISMATCH'


def test_old_prediction_needs_provenance(ctx):
    src=source(ctx)
    with ctx[1].store.tx() as c:
        row=c.execute('SELECT payload FROM predictions WHERE id=?',(src[1],)).fetchone()
        value=json.loads(row[0]);value.pop('execution_identity')
        c.execute('UPDATE predictions SET payload=? WHERE id=?',(json.dumps(value),src[1]))
    result=create(ctx,src)
    assert result.status_code==409 and result.json()['code']=='PROVENANCE_REQUIRED'


def test_queue_limit_and_nonresetting_compute_deadline(ctx):
    src=source(ctx)
    ids=[create(ctx,src).json()['attribution_id'] for _ in range(10)]
    assert create(ctx,src).status_code==429
    ctx[1].run_once()
    with ctx[1].store.tx() as c:
        row=c.execute('SELECT compute_deadline FROM attribution_jobs WHERE id=?',(ids[0],)).fetchone()
        first=row[0]
    ctx[1].run_once()
    with ctx[1].store.tx() as c:
        assert c.execute('SELECT compute_deadline FROM attribution_jobs WHERE id=?',(ids[0],)).fetchone()[0]==first
        c.execute('UPDATE attribution_jobs SET compute_deadline=? WHERE id=?',(time.time()-1,ids[0]))
    assert ctx[0].get('/api/v1/attributions/'+ids[0]).json()['error']['code']=='COMPUTE_TIMEOUT'


def test_restart_resume_duplicate_commit_and_source_edit(ctx):
    src=source(ctx);a=create(ctx,src).json()['attribution_id'];ctx[1].run_once()
    with ctx[1].store.tx() as c:
        saved=c.execute('SELECT * FROM attribution_coalitions WHERE job_id=?',(a,)).fetchall()
        assert saved
        row=saved[0]
        c.execute('INSERT OR IGNORE INTO attribution_coalitions(job_id,coalition_mask,val,outputs_json) VALUES(?,?,?,?)',tuple(row))
        assert c.execute('SELECT COUNT(*) FROM attribution_coalitions WHERE job_id=?',(a,)).fetchone()[0]==len(saved)
    ctx2=(ctx[0],Worker(ctx[1].store.runtime,ctx[2],batch_size=2),ctx[2])
    assert drain(ctx2,a)['status']=='completed'
    result=ctx[0].get('/api/v1/jobs/'+src[0]).json()['result']
    edited=ctx[0].patch('/api/v1/items/'+result['id']+'/text',json=dict(text='Nội dung mới.',expected_revision=1))
    assert edited.status_code==200
    assert ctx[0].get('/api/v1/attributions/'+a).status_code==409


def test_cancel_running_fences_late_batch_and_expiry(ctx):
    src=source(ctx);a=create(ctx,src).json()['attribution_id']
    job=ctx[1].claim_attribution()
    assert job['id']==a
    assert ctx[0].post('/api/v1/attributions/'+a+'/cancel').json()['status']=='cancelled'
    assert ctx[1]._run_attribution_once(job)
    assert ctx[1].store.get_attribution(a)['status']=='cancelled'
    with ctx[1].store.tx() as c:
        c.execute('UPDATE datasets SET expires_at=? WHERE id=(SELECT dataset_id FROM runs WHERE id=(SELECT run_id FROM jobs WHERE id=?))',(time.time()-1,src[0]))
    assert create(ctx,src).status_code==410
