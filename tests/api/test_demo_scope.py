"""Aggregate/drill-down identity checks, including mutations between requests."""
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.worker import Worker
from tests.support import TestOnlyRegistry


@pytest.fixture
def env(tmp_path):
    registry = TestOnlyRegistry()
    # Every row is Negative / topic 2, with real worker provenance.
    def negative(prediction):
        prediction['sentiment'] = {'label_id': 2, 'scores': [.03, .03, .91, .03]}
        prediction['topic'] = {'label_id': 2, 'scores': [.01, .01, .91] + [.01] * 7}
    registry.bad = negative
    app = create_app(tmp_path, registry)
    with TestClient(app) as client:
        worker = Worker(tmp_path, registry)
        dataset = client.post('/api/v1/datasets', json={
            'name': 'Scope fixture', 'profile': 'neu',
            'items': [{'text': f'Phản hồi số {n}'} for n in range(7)]}).json()
        run = client.post('/api/v1/analysis-runs', json={'dataset_id': dataset['id']}).json()
        while worker.run_once():
            pass
        yield client, app.state.store, registry, worker, dataset, run


def get_summary(client, dataset, **params):
    response = client.get(f"/api/v1/datasets/{dataset['id']}/summary", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def drill(client, dataset, summary, **extra):
    params = dict(label_source=summary['label_source'], topic=2, sentiment=2,
                  scope_token=summary['scope_token'], expected_run_id=summary['resolved_run_id'],
                  page_size=5, **extra)
    if summary['revision_scope'] == 'run':
        params['run_id'] = summary['resolved_run_id']
    return client.get(f"/api/v1/datasets/{dataset['id']}/items", params=params)


def test_current_scope_pagination_and_label_source(env):
    client, store, _, _, dataset, run = env
    summary = get_summary(client, dataset)
    assert summary['attention']['topics'][0]['negative_count'] == 7
    assert summary['revision_scope'] == 'current'
    one = drill(client, dataset, summary, page=1).json()
    two = drill(client, dataset, summary, page=2).json()
    assert one['scope_token'] == two['scope_token'] == summary['scope_token']
    assert one['resolved_run_id'] == two['resolved_run_id'] == run['id']
    assert one['total'] == two['total'] == 7
    assert len(one['items']) == 5 and len(two['items']) == 2
    actual = [i['id'] for i in one['items'] + two['items']]
    assert actual == [i['id'] for i in store.query_items(dataset['id'], {})]
    ai = get_summary(client, dataset, label_source='ai')
    assert ai['scope_token'] != summary['scope_token']
    assert drill(client, dataset, ai).status_code == 200
    wrong = dict(ai, scope_token=summary['scope_token'])
    assert drill(client, dataset, wrong).status_code == 409


@pytest.mark.parametrize('change', ['review', 'revision', 'run', 'add'])
def test_changed_scope_rejects_old_summary_even_same_run(env, change):
    client, store, registry, worker, dataset, run = env
    summary = get_summary(client, dataset)
    item = store.query_items(dataset['id'], {})[0]
    if change == 'review':
        response = client.put(f"/api/v1/items/{item['id']}/review", json={
            'task': 'sentiment', 'status': 'corrected', 'label_id': 1,
            'expected_revision': item['revision'], 'expected_review_revision': 0,
            'run_id': run['id'], 'source_prediction_id': item['prediction']['id']})
        assert response.status_code == 200, response.text
    elif change == 'revision':
        assert client.patch(f"/api/v1/items/{item['id']}/text", json={
            'text': 'Nội dung đã đổi', 'expected_revision': 1}).status_code == 200
    elif change == 'run':
        registry.bad = lambda p: p.update(sentiment={'label_id': 1, 'scores': [.03, .91, .03, .03]})
        newer = client.post('/api/v1/analysis-runs', json={'dataset_id': dataset['id']}).json()
        while worker.run_once():
            pass
        assert newer['id'] != run['id']
    else:
        assert client.post(f"/api/v1/datasets/{dataset['id']}/items", json={
            'items': [{'text': 'Một phản hồi mới'}]}).status_code == 201
    # Negative control: the unguarded storage query really has moved away from
    # the old aggregate. A same-run review changes the effective set too.
    unguarded = store.items_page(dataset['id'], {'topic': 2, 'sentiment': 2})
    if change in {'review', 'revision', 'run'}:
        assert unguarded['total'] != 7
    response = drill(client, dataset, summary)
    assert response.status_code == 409, response.text
    assert response.json()['code'] == 'SCOPE_CHANGED'
    refreshed = get_summary(client, dataset)
    assert refreshed['scope_token'] != summary['scope_token']
    assert drill(client, dataset, refreshed).status_code == 200
    if directory := os.environ.get('FIX_EVIDENCE_DIR'):
        Path(directory, f'scope-{change}.json').write_text(json.dumps({
            'before': summary, 'after': refreshed, 'unguarded_total': unguarded['total'],
            'rejected_status': response.status_code, 'item_id': item['id']}, ensure_ascii=False, indent=2), encoding='utf-8')


def test_historical_scope_keeps_both_aggregate_and_items_historical(env):
    client, _, _, _, dataset, run = env
    summary = get_summary(client, dataset, run_id=run['id'], label_source='ai')
    assert summary['revision_scope'] == 'run'
    page = drill(client, dataset, summary)
    assert page.status_code == 200, page.text
    assert page.json()['revision_scope'] == summary['revision_scope']
    assert page.json()['total'] == summary['attention']['topics'][0]['negative_count'] == 7
