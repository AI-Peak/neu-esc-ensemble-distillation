"""Source guards migrated from the retired explanation flow to attribution.

Provider-specific prompt/transport/cache tests were removed with that service.
These software-only regressions keep the prediction validation and source lifetime
boundaries that also protect the replacement attribution jobs.
"""
import json
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from services.api.main import create_app
from services.worker import Worker
from tests.support import TestOnlyRegistry


@pytest.fixture
def env(tmp_path):
    registry = TestOnlyRegistry()
    app = create_app(tmp_path, registry=registry)
    worker = Worker(tmp_path, registry)
    with TestClient(app) as client:
        yield client, worker, app.state.store


def completed(env):
    client, worker, _ = env
    quick = client.post('/api/v1/quick-analysis', json={
        'profile': 'neu', 'text': 'Dịch vụ rất tốt luôn'}).json()
    assert worker.run_once()
    job = client.get('/api/v1/jobs/' + quick['job_id']).json()
    assert job['status'] == 'completed'
    return quick, job['result']


def post_attribution(client, quick, prediction_id, **kwargs):
    return client.post('/api/v1/quick-analysis/' + quick['job_id'] + '/attribution',
                       json={'source_prediction_id': prediction_id,
                             'target': {'kind': 'polarity_margin'}},
                       headers={'Idempotency-Key': str(uuid4()), **kwargs})


@pytest.mark.parametrize('mutation', [
    'absent', 'short', 'oversize', 'null', 'nonfinite', 'range', 'label',
    'schema', 'model', 'revision', 'item', 'warnings', 'token_count'])
def test_invalid_source_prediction_cannot_create_attribution(env, mutation):
    client, _, store = env
    quick, item = completed(env)
    prediction_id = item['prediction']['id']
    with store.tx() as db:
        row = db.execute('SELECT payload FROM predictions WHERE id=?', (prediction_id,)).fetchone()
        payload = json.loads(row['payload'])
        if mutation == 'absent':
            payload.pop('topic')
        elif mutation == 'short':
            payload['topic']['scores'] = [0.9]
        elif mutation == 'oversize':
            payload['topic']['scores'].append(0)
        elif mutation == 'null':
            payload['topic']['scores'] = None
        elif mutation == 'nonfinite':
            payload['topic']['scores'][0] = float('nan')
        elif mutation == 'range':
            payload['topic']['scores'][0] = 1.2
        elif mutation == 'label':
            payload['topic']['label_id'] = 15
        elif mutation in ('warnings', 'token_count'):
            payload.pop('warnings' if mutation == 'warnings' else 'token_count_before_truncation')
        else:
            payload[{'schema': 'schema_id', 'model': 'model_id',
                     'revision': 'revision_id', 'item': 'item_id'}[mutation]] = 'wrong-identity'
        db.execute('UPDATE predictions SET payload=? WHERE id=?', (json.dumps(payload), prediction_id))
    response = post_attribution(client, quick, prediction_id)
    assert response.status_code == 409, response.text
    assert response.json()['code'] == 'INVALID_PREDICTION'
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM attribution_jobs').fetchone()[0] == 0


@pytest.mark.parametrize('change, expected', [('revision', 409), ('expiry', 410), ('delete', 404)])
def test_source_lifetime_is_checked_before_create_and_get(env, change, expected):
    client, _, store = env
    quick, item = completed(env)
    prediction_id = item['prediction']['id']
    created = post_attribution(client, quick, prediction_id)
    assert created.status_code == 202, created.text
    handle = created.json()['attribution_id']
    if change == 'revision':
        store.edit_text(item['id'], 'Nội dung nguồn đã sửa', item['revision'])
    else:
        with store.tx() as db:
            if change == 'expiry':
                db.execute('UPDATE datasets SET expires_at=? WHERE id=?',
                           (time.time() - 1, item['dataset_id']))
            else:
                db.execute('DELETE FROM datasets WHERE id=?', (item['dataset_id'],))
    response = post_attribution(client, quick, prediction_id)
    assert response.status_code == expected, response.text
    response = client.get('/api/v1/attributions/' + handle)
    assert response.status_code == expected, response.text


def test_not_ready_and_wrong_prediction_are_conflicts(env):
    client, worker, _ = env
    quick = client.post('/api/v1/quick-analysis', json={
        'profile': 'neu', 'text': 'Học phí học kỳ này cao quá.'}).json()
    response = post_attribution(client, quick, 'not-ready')
    assert response.status_code == 409 and response.json()['code'] == 'JOB_NOT_READY'
    worker.run_once()
    response = post_attribution(client, quick, 'wrong-prediction')
    assert response.status_code == 409 and response.json()['code'] == 'SOURCE_CONFLICT'


@pytest.mark.parametrize('origin, host, expected', [
    (None, None, 202), ('http://testserver', None, 202),
    ('http://localhost:8765', '127.0.0.1:8765', 202),
    ('https://external.invalid', None, 403),
    ('http://localhost.evil.invalid:8765', '127.0.0.1:8765', 403),
    ('http://localhost:8766', '127.0.0.1:8765', 403),
])
def test_attribution_origin_guard_replaces_explanation_origin_guard(env, origin, host, expected):
    client, _, _ = env
    quick, item = completed(env)
    headers = {}
    if origin:
        headers['Origin'] = origin
    if host:
        headers['Host'] = host
    response = post_attribution(client, quick, item['prediction']['id'], **headers)
    assert response.status_code == expected, response.text
