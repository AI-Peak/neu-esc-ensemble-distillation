"""Quick-source sensitivity regressions; all inference uses TestOnlyRegistry."""
import copy
import hashlib
import json
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import pytest

from services.storage.db import DomainError, Store, encode
from tests.api.test_sensitivity import env, _build_payload, _drain, _items


def _quick(env, text="Dịch vụ rất tốt 👩‍💻 nhưng phòng nóng", profile="neu"):
    client, store, registry, worker = env
    quick = client.post('/api/v1/quick-analysis', json={'text': text, 'profile': profile})
    assert quick.status_code == 202, quick.text
    quick = quick.json()
    _drain(worker)
    job = client.get(f"/api/v1/jobs/{quick['job_id']}").json()
    assert job['status'] == 'completed' and job['kind'] == 'quick'
    return quick, job['result']


def _create(env, quick, item, key='quick-sensitivity', needle='rất tốt'):
    client = env[0]
    return client.post(f"/api/v1/items/{item['id']}/sensitivity-experiments",
                       json=_build_payload(item, needle, run_id=quick['run_id']),
                       headers={'Idempotency-Key': key})


def _expiry(store, item):
    with store.tx() as c:
        c.execute('UPDATE datasets SET expires_at=? WHERE id=?', (time.time()-1, item['dataset_id']))


@pytest.mark.parametrize('profile', ['neu', 'uit'])
def test_quick_source_pair_keeps_provenance_unicode_and_source_unchanged(env, profile):
    client, store, registry, worker = env
    quick, item = _quick(env, profile=profile)
    original = copy.deepcopy(item)
    response = _create(env, quick, item)
    assert response.status_code == 202, response.text
    exp = response.json()
    source = exp['source']
    assert source == {'item_id': item['id'], 'revision_id': item['revision_id'],
                      'revision': item['revision'],
                      'text_sha256': hashlib.sha256(item['text'].encode()).hexdigest(),
                      'selected_run_id': quick['run_id'], 'resolved_run_id': quick['run_id'],
                      'prediction_id': item['prediction']['id']}
    assert exp['execution']['model_id'] == item['prediction']['model_id']
    assert exp['execution']['model_version'] == item['prediction']['model_version']
    assert exp['execution']['schema_id'] == item['prediction']['schema_id']
    assert exp['execution']['baseline_recomputed'] is True
    with store.connect() as c:
        source_expiry = c.execute('SELECT expires_at FROM datasets WHERE id=?', (item['dataset_id'],)).fetchone()[0]
    assert datetime.fromisoformat(exp['expires_at'].replace('Z', '+00:00')).timestamp() <= source_expiry
    _drain(worker)
    done = client.get(f"/api/v1/sensitivity-experiments/{exp['experiment_id']}").json()
    assert done['status'] == 'completed' and done['result'] is not None
    assert datetime.fromisoformat(done['expires_at'].replace('Z', '+00:00')).timestamp() <= source_expiry
    assert done['result']['baseline']['text'] == item['text']
    assert done['result']['variant']['text'] == item['text'].replace('rất tốt', '', 1)
    assert done['result']['baseline']['prediction']['id'] != item['prediction']['id']
    assert client.get(f"/api/v1/items/{item['id']}").json() == original
    assert client.get('/api/v1/datasets').json() == []
    # Emoji selection is converted by exact UTF-16 code units, never Python offsets.
    again = _create(env, quick, item, 'quick-emoji', '👩‍💻')
    assert again.status_code == 202, again.text
    assert again.json()['variant_text'] == item['text'].replace('👩‍💻', '')
    _drain(worker)
    with store.connect() as c:
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('status', ['queued', 'failed', 'cancelled', 'interrupted'])
def test_quick_source_requires_successful_completed_job(env, status):
    quick, item = _quick(env)
    with env[1].tx() as c:
        c.execute('UPDATE jobs SET status=? WHERE id=?', (status, quick['job_id']))
        c.execute('UPDATE runs SET status=? WHERE id=?', (status, quick['run_id']))
    response = _create(env, quick, item)
    assert response.status_code == 409 and response.json()['code'] == 'JOB_NOT_READY'


@pytest.mark.parametrize('mutation', ['prediction_id', 'schema_id', 'model_id', 'item_id', 'revision_id', 'scores'])
def test_quick_source_rejects_mismatched_prediction_and_identity(env, mutation):
    quick, item = _quick(env)
    if mutation == 'prediction_id':
        item['prediction']['id'] = 'wrong-id'
    else:
        with env[1].tx() as c:
            row = c.execute('SELECT payload FROM predictions WHERE id=?', (item['prediction']['id'],)).fetchone()
            prediction = json.loads(row['payload'])
            if mutation == 'scores':
                prediction['topic']['scores'] = [0.9]
            else:
                prediction[mutation] = 'wrong-identity'
            c.execute('UPDATE predictions SET payload=? WHERE id=?', (encode(prediction), item['prediction']['id']))
    response = _create(env, quick, item)
    assert response.status_code == 409, response.text
    assert response.json()['code'] == ('SOURCE_CONFLICT' if mutation == 'prediction_id' else 'INVALID_PREDICTION')
    with env[1].connect() as c:
        assert c.execute('SELECT COUNT(*) FROM sensitivity_experiments').fetchone()[0] == 0


def test_quick_source_stale_and_known_expiry_validation(env):
    client, store, _, _ = env
    quick, item = _quick(env)
    edited = client.patch(f"/api/v1/items/{item['id']}/text",
                          json={'text': 'Nguồn đã sửa', 'expected_revision': item['revision']})
    assert edited.status_code == 200
    rejected = _create(env, quick, item)
    assert rejected.status_code == 409 and rejected.json()['code'] == 'REVISION_CONFLICT'
    other_quick, other_item = _quick(env)
    _expiry(store, other_item)
    with store.connect() as c, pytest.raises(DomainError) as error:
        store.validate_quick_source(c, other_quick['job_id'], other_item['prediction']['id'])
    assert error.value.status == 410 and error.value.code == 'JOB_EXPIRED'
    expired = _create(env, other_quick, other_item, 'expired-before-create')
    assert expired.status_code == 404
    store.cleanup()
    assert client.get(f"/api/v1/jobs/{other_quick['job_id']}").status_code == 404


def test_quick_cancel_retry_then_expiry_removes_both_datasets(env):
    client, store, _, worker = env
    quick, item = _quick(env)
    created = _create(env, quick, item)
    assert created.status_code == 202, created.text
    exp = created.json()
    assert client.post(f"/api/v1/jobs/{exp['job_id']}/cancel").json()['status'] == 'cancelled'
    assert client.post(f"/api/v1/jobs/{exp['job_id']}/retry").json()['status'] == 'queued'
    _drain(worker)
    assert client.get(f"/api/v1/sensitivity-experiments/{exp['experiment_id']}").json()['result'] is not None
    _expiry(store, item)
    assert client.get(f"/api/v1/sensitivity-experiments/{exp['experiment_id']}").status_code == 404
    assert client.post(f"/api/v1/jobs/{exp['job_id']}/retry").status_code == 404
    store.cleanup()
    with store.connect() as c:
        for table in ['datasets', 'jobs', 'items', 'sensitivity_experiments', 'idempotency']:
            assert c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0, table
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('change', ['expire', 'delete', 'expire-cleanup'])
def test_quick_source_disappearing_during_pair_fences_late_outputs_and_worker_recovers(env, change):
    client, store, registry, worker = env
    quick, item = _quick(env)
    response = _create(env, quick, item)
    assert response.status_code == 202, response.text
    exp = response.json()
    started, release = threading.Event(), threading.Event()
    def gate(*_):
        started.set()
        assert release.wait(10), 'test pair gate timed out'
    registry.pair_hook = gate
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(worker.run_once)
        assert started.wait(5), 'pair inference never started'
        try:
            if change == 'delete':
                store.delete_dataset(item['dataset_id'])
            else:
                _expiry(store, item)
                if change == 'expire-cleanup':
                    store.cleanup()
        finally:
            release.set()
        assert future.result(timeout=10) is True
    assert client.get(f"/api/v1/sensitivity-experiments/{exp['experiment_id']}").status_code == 404
    with store.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM datasets').fetchone()[0] == 0
        assert c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []
    registry.pair_hook = None
    # The same worker can subsequently process a fresh job, without orphan loops.
    new_quick, new_item = _quick(env)
    assert new_quick['job_id'] != quick['job_id']
    assert new_item['prediction'] is not None


@pytest.mark.parametrize('kind', ['unmarked', 'multi-item', 'multi-run'])
def test_unsupported_temporary_sources_are_still_rejected(env, kind):
    client, store, registry, worker = env
    if kind == 'unmarked':
        dataset = store.create_dataset({'name': 'Other temporary source', 'profile': 'neu',
                                        'items': [{'text': 'Dịch vụ rất tốt'}]}, temporary=True)
        run = store.create_run(dataset['id'], registry.status('neu'))
        _drain(worker)
        item = _items(client, dataset['id'])[0]
        quick = {'run_id': run['id']}
    else:
        quick, item = _quick(env)
        if kind == 'multi-item':
            store.add_items(item['dataset_id'], [{'text': 'Another item'}])
        else:
            store.create_run(item['dataset_id'], registry.status('neu'))
            _drain(worker)
    response = _create(env, quick, item)
    assert response.status_code == 422 and response.json()['code'] == 'INVALID_EXPERIMENT_SOURCE', response.text


def test_quick_stale_after_creation_blocks_result_and_retry_without_committing_pair(env):
    client, store, registry, worker = env
    quick, item = _quick(env)
    created = _create(env, quick, item)
    assert created.status_code == 202, created.text
    exp = created.json()
    def change_source(*_):
        changed = client.patch(f"/api/v1/items/{item['id']}/text",
                               json={'text': 'Nguồn đã thay đổi khi đang chạy', 'expected_revision': 1})
        assert changed.status_code == 200
    registry.pair_hook = change_source
    assert worker.run_once()
    job = client.get(f"/api/v1/jobs/{exp['job_id']}").json()
    assert job['status'] == 'failed' and job['completed'] == 0
    assert 'SOURCE_CONTEXT_CHANGED' in job['error']
    read = client.get(f"/api/v1/sensitivity-experiments/{exp['experiment_id']}")
    assert read.status_code == 409 and read.json()['code'] == 'REVISION_CONFLICT'
    retry = client.post(f"/api/v1/jobs/{exp['job_id']}/retry")
    assert retry.status_code == 409 and retry.json()['code'] == 'REVISION_CONFLICT'
    with store.connect() as c:
        run_id = c.execute('SELECT run_id FROM jobs WHERE id=?', (exp['job_id'],)).fetchone()[0]
        assert c.execute('SELECT COUNT(*) FROM predictions WHERE run_id=?', (run_id,)).fetchone()[0] == 0


def test_quick_selection_rejects_splitting_unicode_and_forged_revision(env):
    client, store, _, _ = env
    quick, item = _quick(env)
    payload = _build_payload(item, '👩‍💻', run_id=quick['run_id'])
    payload['selection']['start_utf16'] += 1
    split = client.post(f"/api/v1/items/{item['id']}/sensitivity-experiments", json=payload,
                        headers={'Idempotency-Key': 'split-emoji'})
    assert split.status_code == 422 and split.json()['code'] == 'INVALID_SELECTION'
    assert split.json()['details']['reason'] == 'SURROGATE_BOUNDARY'
    payload = _build_payload(item, 'rất tốt', run_id=quick['run_id'])
    payload['expected_revision'] += 1
    stale = client.post(f"/api/v1/items/{item['id']}/sensitivity-experiments", json=payload,
                        headers={'Idempotency-Key': 'forged-revision'})
    assert stale.status_code == 409 and stale.json()['code'] == 'REVISION_CONFLICT'
    with store.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM sensitivity_experiments').fetchone()[0] == 0
