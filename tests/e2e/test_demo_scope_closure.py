"""Demo scope/ranking/routing acceptance through isolated test-only workers."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import time

import httpx
import pytest
from playwright.sync_api import expect


def text_for(sentiment, topic, index=0):
    for n in range(10000):
        text = f'Phản hồi kiểm thử {index} {n}'
        value = sum(map(ord, text))
        if value % 4 == sentiment and value % 10 == topic:
            return text
    raise AssertionError('No deterministic fixture text')


def create(client, name, texts):
    response = client.post('/datasets', json={'name': name, 'profile': 'neu',
                                            'items': [{'text': t} for t in texts]})
    assert response.status_code == 201, response.text
    return response.json()


def analyze(client, dataset):
    response = client.post('/analysis-runs', json={'dataset_id': dataset['id']})
    assert response.status_code == 202, response.text
    run = response.json()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = client.get('/jobs/' + run['job_id']).json()
        if job['status'] == 'completed':
            return run
        assert job['status'] not in {'failed', 'cancelled', 'interrupted'}, job
        time.sleep(.02)
    raise AssertionError('Test worker did not complete')


def observe(name, value):
    if directory := os.environ.get('FIX_EVIDENCE_DIR'):
        Path(directory, name + '.json').write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


@contextmanager
def route_safe_page(context):
    page = context.new_page()
    try:
        yield page
    finally:
        # Suppress late route.fetch callbacks before the browser context closes,
        # including when an assertion ends a test with requests still in flight.
        page.unroute_all(behavior='ignoreErrors')


def summary(client, dataset, source='effective'):
    response = client.get(f"/datasets/{dataset['id']}/summary", params={'label_source': source})
    assert response.status_code == 200, response.text
    return response.json()


def scoped_items(client, dataset, snapshot, *, page=1, filtered=True):
    params = dict(label_source=snapshot['label_source'], scope_token=snapshot['scope_token'],
                  expected_run_id=snapshot['resolved_run_id'] or '', page=page, page_size=10)
    if filtered:
        params.update(sentiment=2, topic=2)
    return client.get(f"/datasets/{dataset['id']}/items", params=params)


def test_no_hash_demo_workspace_entry_reload_back_forward_help(browser, app_server):
    with browser.new_context() as context:
        page = context.new_page()
        calls = []
        page.on('request', lambda r: calls.append(r.url) if r.method == 'POST' and '/quick-analysis' in r.url else None)
        page.goto(app_server.url)
        expect(page.locator('#sentence')).to_be_visible()
        expect(page.locator('.sidebar')).to_have_count(0)
        page.reload()
        expect(page.locator('#sentence')).to_be_visible()
        page.goto(app_server.url + '/#/')
        expect(page.get_by_test_id('create-dataset')).to_be_visible()
        page.get_by_role('button', name='Thử một câu', exact=True).first.click()
        expect(page).to_have_url(re.compile(r'#/demo$'))
        expect(page.locator('#sentence')).to_be_visible()
        page.go_back()
        expect(page.get_by_test_id('create-dataset')).to_be_visible()
        page.go_forward()
        expect(page.locator('#sentence')).to_be_visible()
        page.goto(app_server.url + '/#/help')
        expect(page.get_by_role('heading', name='Trạng thái & hướng dẫn')).to_be_visible()
        expect(page.get_by_role('heading', name='Đối chiếu từ ngữ với dự đoán')).to_be_visible()
        expect(page.locator('.prose')).to_contain_text('classifier local')
        expect(page.locator('.prose')).not_to_contain_text('FEEDBACK_EXPLANATION_')
        expect(page.locator('.prose')).not_to_contain_text('9router')
        page.goto(app_server.url + '/#/research')
        expect(page.get_by_role('heading', name='Báo cáo nghiên cứu', exact=True)).to_be_visible()
        page.goto(app_server.url + '/#/new')
        expect(page.get_by_test_id('dataset-name')).to_be_visible()
        assert calls == []


def test_workspace_scope_review_run_pagination_and_label_source_api(app_server):
    """Workspace multirow guards remain API contracts after demo drops selection."""
    with httpx.Client(base_url=app_server.url + '/api/v1') as client:
        dataset = create(client, 'Scope seventeen rows', [text_for(2, 2, n) for n in range(17)])
        other = create(client, 'Scope other dataset', [text_for(2, 4, 20)])
        run_a = analyze(client, dataset)
        original = summary(client, dataset)
        assert original['total'] == original['attention']['eligible_count'] == 17
        assert original['attention']['topics'][0]['negative_count'] == 17
        first_response = scoped_items(client, dataset, original)
        second_response = scoped_items(client, dataset, original, page=2)
        assert first_response.status_code == second_response.status_code == 200
        first, second = first_response.json(), second_response.json()
        assert first['resolved_run_id'] == run_a['id'] and first['revision_scope'] == 'current'
        assert first['label_source'] == 'effective' and first['dataset_id'] == dataset['id']
        assert first['scope_token'] == second['scope_token'] == original['scope_token']
        assert first['total'] == second['total'] == 17
        assert len(first['items']) == 10 and len(second['items']) == 7
        expected_ids = [item['id'] for item in client.get(f"/datasets/{dataset['id']}/items").json()['items']]
        assert [item['id'] for item in first['items'] + second['items']] == expected_ids
        item = first['items'][0]
        review = client.put(f"/items/{item['id']}/review", json={
            'task': 'sentiment', 'status': 'corrected', 'label_id': 1,
            'expected_revision': 1, 'expected_review_revision': 0,
            'run_id': run_a['id'], 'source_prediction_id': item['prediction']['id']})
        assert review.status_code == 200, review.text
        stale_review = scoped_items(client, dataset, original)
        assert stale_review.status_code == 409, stale_review.text
        effective = summary(client, dataset)
        assert effective['scope_token'] != original['scope_token']
        assert effective['resolved_run_id'] == run_a['id']
        assert effective['attention']['topics'][0]['negative_count'] == 16
        assert scoped_items(client, dataset, effective).json()['total'] == 16
        ai = summary(client, dataset, 'ai')
        assert ai['scope_token'] != effective['scope_token']
        assert ai['attention']['topics'][0]['negative_count'] == 17
        ai_page = scoped_items(client, dataset, ai).json()
        assert ai_page['total'] == 17
        reviewed = next(row for row in ai_page['items'] if row['id'] == item['id'])
        assert reviewed['prediction']['sentiment']['label_id'] == 2
        assert reviewed['effective']['sentiment'] == 1
        for row in client.get(f"/datasets/{dataset['id']}/items").json()['items']:
            edited = client.patch(f"/items/{row['id']}/text", json={
                'text': text_for(1, 3, row['source_row'] + 100), 'expected_revision': 1})
            assert edited.status_code == 200, edited.text
        run_b = analyze(client, dataset)
        stale_run = scoped_items(client, dataset, ai, page=2)
        assert stale_run.status_code == 409, stale_run.text
        current = summary(client, dataset, 'ai')
        assert current['resolved_run_id'] == run_b['id'] != run_a['id']
        assert current['attention']['topics'][0]['negative_count'] == 0
        assert scoped_items(client, dataset, current).json()['total'] == 0
        unrelated = summary(client, other, 'ai')
        assert unrelated['attention']['eligible_count'] == 0 and unrelated['processed'] == 0
        assert unrelated['scope_token'] != current['scope_token']
        observe('workspace-scope-api', {'run_a': run_a['id'], 'run_b': run_b['id'],
            'item_ids': expected_ids, 'page1': first, 'page2': second,
            'stale_review_status': stale_review.status_code, 'stale_run_status': stale_run.status_code})


def test_workspace_ranking_toxic_missing_empty_and_partial_api(app_server):
    with httpx.Client(base_url=app_server.url + '/api/v1') as client:
        texts = ([text_for(2, 2, n) for n in range(6)] + [text_for(0, 2, 20+n) for n in range(4)]
                 + [text_for(2, 4, 40+n) for n in range(2)] + [text_for(3, 3, 60+n) for n in range(2)])
        dataset = create(client, 'Ranking Toxic known counts', texts)
        analyze(client, dataset)
        empty = create(client, 'Unprocessed known counts', ['Một câu chưa phân tích'])
        ranked = summary(client, dataset)
        topics = ranked['attention']['topics']
        assert [row['topic_id'] for row in topics] == [2, 4, 3]
        assert [(row['negative_count'], row['eligible_count']) for row in topics] == [(6, 10), (2, 2), (0, 2)]
        assert topics[0]['negative_rate'] == .6 and topics[1]['negative_rate'] == 1
        assert topics[2]['toxic_count'] == 2 and topics[1]['small_sample']
        added = client.post(f"/datasets/{dataset['id']}/items", json={'items': [{'text': 'Chưa có nhãn mới'}]})
        assert added.status_code == 201, added.text
        partial = summary(client, dataset)
        assert partial['total'] == 15 and partial['processed'] == 14
        assert partial['attention']['eligible_count'] == 14
        assert partial['attention']['missing_topic_count'] == 1
        unprocessed = summary(client, empty)
        assert unprocessed['total'] == 1 and unprocessed['processed'] == 0
        assert unprocessed['denominator'] == {'sentiment': 0, 'topic': 0, 'cross': 0}
        assert unprocessed['attention']['topics'] == []
        with sqlite3.connect(app_server.runtime / 'workspace.sqlite3') as database:
            database.execute('DELETE FROM items WHERE dataset_id=?', (empty['id'],))
        no_rows = summary(client, empty)
        assert no_rows['total'] == no_rows['attention']['eligible_count'] == 0
        assert no_rows['attention']['topics'] == []
        assert no_rows['denominator'] == {'sentiment': 0, 'topic': 0, 'cross': 0}


@pytest.mark.parametrize('status', ['running', 'partial', 'failed', 'cancelled', 'interrupted'])
def test_workspace_incomplete_run_and_missing_label_denominators_api(app_server, status):
    with httpx.Client(base_url=app_server.url + '/api/v1') as client:
        dataset = create(client, 'Incomplete ' + status, [text_for(2, 2, n) for n in range(3)])
        run = analyze(client, dataset)
        items = client.get(f"/datasets/{dataset['id']}/items").json()['items']
        # Only this isolated runtime is mutated into controlled missing/error states.
        with sqlite3.connect(app_server.runtime / 'workspace.sqlite3') as database:
            database.execute('DELETE FROM predictions WHERE run_id=?', (run['id'],))
            database.execute('UPDATE runs SET status=? WHERE id=?', (status, run['id']))
            database.execute('UPDATE jobs SET status=?,lease_owner=NULL,lease_expires_at=NULL WHERE id=?', (status, run['job_id']))
            database.execute('UPDATE run_items SET error=? WHERE run_id=? AND item_id=?', ('Controlled test error', run['id'], items[2]['id']))
        for row, labels in zip(items, [{'sentiment': 3, 'topic': 2}, {'topic': 2}, {'topic': 4}]):
            for task, label in labels.items():
                result = client.put(f"/items/{row['id']}/review", json={
                    'task': task, 'status': 'corrected', 'label_id': label,
                    'expected_revision': 1, 'expected_review_revision': 0})
                assert result.status_code == 200, result.text
        effective = summary(client, dataset)
        assert effective['run_status'] == status and effective['total'] == 3
        assert effective['attention']['eligible_count'] == 1
        assert effective['attention']['missing_sentiment_with_topic_count'] == 2
        assert effective['errors'] == 1 and effective['processed'] == 0
        assert effective['total'] - effective['processed'] - effective['errors'] == 2
        assert effective['denominator'] == {'sentiment': 1, 'topic': 3, 'cross': 1}
        topics = effective['attention']['topics']
        assert topics[0]['topic_id'] == 2 and topics[0]['toxic_count'] == 1
        assert topics[0]['negative_count'] == 0 and topics[0]['eligible_count'] == 1
        assert topics[1]['topic_id'] == 4 and topics[1]['negative_rate'] is None
        ai = summary(client, dataset, 'ai')
        assert ai['attention']['eligible_count'] == 0
        assert ai['attention']['missing_topic_count'] == 3
        assert ai['attention']['topics'] == []
        assert ai['denominator'] == {'sentiment': 0, 'topic': 0, 'cross': 0}


def test_demo_latest_quick_scope_ignores_durable_dataset_and_late_summary(browser, app_server, screenshot_dir):
    with (httpx.Client(base_url=app_server.url + '/api/v1') as client,
          browser.new_context() as context, route_safe_page(context) as page):
        durable = create(client, 'Bộ lưu sẵn không thuộc demo', [text_for(2, 2, n) for n in range(3)])
        analyze(client, durable)
        held, calls = [], []
        hold_first = {'value': True}

        def hold_summary(route):
            if hold_first['value']:
                hold_first['value'] = False
                actual = route.fetch()
                held.append((route, actual, actual.json()))
            else:
                route.continue_()

        page.route('**/api/v1/datasets/*/summary?**', hold_summary)
        page.on('request', lambda request: calls.append(request.url)
                if '/summary?' in request.url or '/network?' in request.url or '/items?' in request.url else None)
        page.goto(app_server.url + '/#/demo')
        expect(page.locator('#dataset-select')).to_have_count(0)
        expect(page.locator('.quick-add-box')).to_have_count(0)
        expect(page.locator('.distribution-pane')).to_have_count(0)
        assert calls == [], 'A durable dataset must not be selected or queried on entry'
        page.locator('#sentence').fill(text_for(2, 2, 101))
        with page.expect_response(lambda response: response.request.method == 'POST'
                                  and response.url.endswith('/quick-analysis')) as created:
            page.locator('#analyze').click()
        quick_a = created.value.json()
        expect(page.locator('#result-content')).to_be_visible()
        deadline = time.monotonic() + 10
        while not held and time.monotonic() < deadline:
            page.wait_for_timeout(10)
        assert len(held) == 1
        old_summary = held[0][2]
        assert old_summary['label_source'] == 'ai' and old_summary['total'] == 1
        assert old_summary['resolved_run_id'] == quick_a['run_id']
        assert old_summary['dataset_id'] != durable['id']
        page.locator('#sentence').fill(text_for(1, 3, 202))
        expect(page.locator('#contribution-donut')).to_have_count(0)
        with page.expect_response(lambda response: response.request.method == 'POST'
                                  and response.url.endswith('/quick-analysis')) as created:
            page.locator('#analyze').click()
        quick_b = created.value.json()
        # The first attribution can still be loading NLP resources while B waits
        # for the worker, followed by the UI's one-second polling interval. This
        # regression verifies scope ownership, rather than a five-second SLA.
        expect(page.locator('#result-content')).to_be_visible(timeout=20000)
        expect(page.locator('.distribution-pane')).to_be_visible()
        expect(page.locator('#distribution-heading')).to_have_text('Tỷ trọng đóng góp của cụm từ')
        expect(page.locator('#evidence-list .evidence-row')).to_have_count(1)
        expect(page.locator('#evidence-list .sentiment-badge')).to_have_text('Tích cực')
        expect(page.locator('#topic-attention .attention-row').first).to_contain_text('0 / 1')
        # The accepted old summary must not replace B, even after transport completes.
        held[0][0].fulfill(response=held[0][1])
        page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        expect(page.locator('#evidence-list .sentiment-badge')).to_have_text('Tích cực')
        expect(page.locator('#evidence-list .evidence-row p')).to_have_text(text_for(1, 3, 202))
        expect(page.locator('#topic-attention .attention-row').first).to_contain_text('0 / 1')
        assert all(f"/datasets/{durable['id']}/" not in url for url in calls)
        b_job = client.get('/jobs/' + quick_b['job_id']).json()
        b_dataset = b_job['result']['dataset_id']
        assert b_dataset != old_summary['dataset_id']
        assert any(f"/datasets/{b_dataset}/summary?label_source=ai" in url for url in calls)
        page.locator('#clear').click()
        expect(page.locator('.distribution-pane')).to_have_count(0)
        expect(page.locator('#evidence-list')).to_have_count(0)
        expect(page.locator('#dataset-select')).to_have_count(0)
        expect(page.locator('#schema-select')).to_have_count(0)
        expect(page.locator('.distribution-pane')).to_have_count(0)
        observe('latest-quick-scope', {'quick_a': quick_a, 'quick_b': quick_b,
                                      'durable_dataset': durable['id'], 'requests': calls})
        page.screenshot(path=str(screenshot_dir / 'latest-quick-scope-reset.png'), full_page=True)
