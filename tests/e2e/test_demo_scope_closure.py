"""Demo scope/ranking/routing acceptance through isolated test-only workers."""
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
        for variable in ['BASE_URL', 'API_KEY', 'MODEL', 'TIMEOUT_SECONDS']:
            expect(page.locator('pre')).to_contain_text('FEEDBACK_EXPLANATION_' + variable)
        expect(page.locator('.prose')).to_contain_text('không tự nạp file .env')
        page.goto(app_server.url + '/#/research')
        expect(page.get_by_role('heading', name='Báo cáo nghiên cứu', exact=True)).to_be_visible()
        page.goto(app_server.url + '/#/new')
        expect(page.get_by_test_id('dataset-name')).to_be_visible()
        assert calls == []


def test_demo_scope_review_run_pagination_source_and_dataset(browser, app_server, screenshot_dir):
    with httpx.Client(base_url=app_server.url + '/api/v1') as client, browser.new_context() as context:
        texts = [text_for(2, 2, n) for n in range(7)]
        dataset = create(client, 'Scope seven rows', texts)
        other = create(client, 'Scope other dataset', [text_for(2, 4, 20)])
        run_a = analyze(client, dataset)
        page = context.new_page()
        page.goto(app_server.url + '/#/demo')
        expect(page.locator('#dataset-select option')).to_have_count(3)
        page.locator('#dataset-select').select_option(dataset['id'])
        evidence = page.locator('.attention-evidence-btn').first
        expect(evidence).to_have_text('Xem 7 phản hồi tiêu cực')
        params = []
        page.on('request', lambda r: params.append(r.url) if '/items?' in r.url else None)
        with page.expect_response(lambda r: '/items?' in r.url and 'scope_token=' in r.url) as response:
            evidence.click()
        first = response.value.json()
        assert first['resolved_run_id'] == run_a['id'] and first['revision_scope'] == 'current'
        assert first['label_source'] == 'effective' and first['dataset_id'] == dataset['id']
        assert first['total'] == 7 and len(first['items']) == 5
        assert 'run_id=' not in params[-1].replace('expected_run_id=', 'expected=')
        with page.expect_response(lambda r: '/items?' in r.url and 'page=2' in r.url) as response:
            page.get_by_role('button', name='Trang sau →', exact=True).last.click()
        second = response.value.json()
        assert len(second['items']) == 2
        expected_ids = [i['id'] for i in client.get(f"/datasets/{dataset['id']}/items").json()['items']]
        assert [i['id'] for i in first['items'] + second['items']] == expected_ids
        item = first['items'][0]
        review = client.put(f"/items/{item['id']}/review", json={
            'task': 'sentiment', 'status': 'corrected', 'label_id': 1,
            'expected_revision': 1, 'expected_review_revision': 0,
            'run_id': run_a['id'], 'source_prediction_id': item['prediction']['id']})
        assert review.status_code == 200, review.text
        # Old effective count and items are invalidated, despite the same run id.
        with page.expect_response(lambda r: '/items?' in r.url) as response:
            page.get_by_role('button', name='← Trang trước', exact=True).last.click()
        assert response.value.status == 409
        expect(evidence).to_have_text('Xem 6 phản hồi tiêu cực')
        with page.expect_response(lambda r: '/items?' in r.url and 'label_source=effective' in r.url) as response:
            evidence.click()
        assert response.value.json()['total'] == 6
        page.get_by_role('button', name='Chỉ dự đoán AI gốc', exact=True).click()
        expect(evidence).to_have_text('Xem 7 phản hồi tiêu cực')
        with page.expect_response(lambda r: '/items?' in r.url and 'label_source=ai' in r.url) as response:
            evidence.click()
        assert response.value.json()['total'] == 7
        for row in client.get(f"/datasets/{dataset['id']}/items").json()['items']:
            assert client.patch(f"/items/{row['id']}/text", json={
                'text': text_for(1, 3, row['source_row'] + 100), 'expected_revision': 1}).status_code == 200
        run_b = analyze(client, dataset)
        with page.expect_response(lambda r: '/items?' in r.url) as response:
            page.get_by_role('button', name='Trang sau →', exact=True).last.click()
        assert response.value.status == 409
        expect(page.locator('.attention-section')).to_contain_text('Chưa có phản hồi gán nhãn Tiêu cực')
        expect(page.locator('.attention-evidence-btn').first).to_be_disabled()
        page.locator('#dataset-select').select_option(other['id'])
        expect(page.locator('.decision-panel')).to_contain_text('Chưa đủ nhãn')
        page.locator('#schema-select').select_option('uit')
        expect(page.locator('#dataset-select')).to_have_value('')
        observe('browser-scope', {'run_a': run_a['id'], 'run_b': run_b['id'],
                                  'item_ids': expected_ids, 'page1': first, 'page2': second,
                                  'requests': params, 'stale_review_status': 409, 'stale_run_status': 409})
        page.screenshot(path=str(screenshot_dir / 'demo-scope-reset.png'), full_page=True)


def test_demo_ranking_toxic_missing_empty_and_partial(browser, app_server, screenshot_dir):
    with httpx.Client(base_url=app_server.url + '/api/v1') as client, browser.new_context() as context:
        texts = ([text_for(2, 2, n) for n in range(6)] + [text_for(0, 2, 20+n) for n in range(4)]
                 + [text_for(2, 4, 40+n) for n in range(2)] + [text_for(3, 3, 60+n) for n in range(2)])
        dataset = create(client, 'Ranking Toxic known counts', texts)
        analyze(client, dataset)
        empty = create(client, 'Unprocessed known counts', ['Một câu chưa phân tích'])
        page = context.new_page()
        page.goto(app_server.url + '/#/demo')
        page.locator('#dataset-select').select_option(dataset['id'])
        rows = page.locator('.attention-table tbody tr')
        expect(rows).to_have_count(3)
        expect(rows.nth(0)).to_contain_text('6/10 · 60,0%')
        expect(rows.nth(1)).to_contain_text('2/2 · 100,0%')
        expect(rows.nth(2).locator('[data-label="Toxic"]')).to_have_text('2')
        expect(rows.nth(2).locator('[data-label="Tiêu cực"]')).to_have_text('0')
        expect(rows.nth(1)).to_contain_text('Ít dữ liệu')
        expect(page.locator('.priority-note')).to_contain_text('nhiều phản hồi tiêu cực nhất')
        expect(page.locator('.decision-panel')).not_to_contain_text('cao nhất trong tập')
        page.screenshot(path=str(screenshot_dir / 'demo-layer3-ranking-toxic.png'), full_page=True)
        page.set_viewport_size({'width': 320, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert rows.nth(0).locator('.attention-topic-name').evaluate('el => parseFloat(getComputedStyle(el).fontSize)') >= 14
        assert rows.nth(0).locator('[data-label="Tiêu cực"]').evaluate('el => parseFloat(getComputedStyle(el,"::before").fontSize)') >= 14
        page.screenshot(path=str(screenshot_dir / 'demo-layer3-ranking-toxic-320.png'), full_page=True)
        page.set_viewport_size({'width': 1280, 'height': 900})
        # Add an unprocessed row; it must count as missing rather than as 0%.
        client.post(f"/datasets/{dataset['id']}/items", json={'items': [{'text': 'Chưa có nhãn mới'}]})
        page.reload()
        page.locator('#dataset-select').select_option(dataset['id'])
        expect(page.locator('.attention-denominator')).to_contain_text('14/15')
        expect(page.locator('.attention-denominator')).to_contain_text('1 dòng thiếu chủ đề')
        expect(page.locator('.attention-section')).to_contain_text('1 dòng chưa xử lý')
        page.screenshot(path=str(screenshot_dir / 'demo-layer3-partial-missing.png'), full_page=True)
        page.locator('#dataset-select').select_option(empty['id'])
        expect(page.locator('.attention-section')).to_contain_text('Chưa đủ nhãn')
        expect(page.locator('.decision-panel')).not_to_contain_text('Chưa có vấn đề nổi cộm')
        page.screenshot(path=str(screenshot_dir / 'demo-layer3-unprocessed.png'), full_page=True)
        with sqlite3.connect(app_server.runtime / 'workspace.sqlite3') as database:
            database.execute('DELETE FROM items WHERE dataset_id=?', (empty['id'],))
        page.reload()
        page.locator('#dataset-select').select_option(empty['id'])
        expect(page.locator('.attention-section')).to_contain_text('Chưa đủ nhãn')
        expect(page.locator('.attention-section tbody tr')).to_have_count(0)
        expect(page.locator('.decision-panel')).not_to_contain_text('NaN')
        expect(page.locator('.decision-panel')).not_to_contain_text('0,0%')
        page.screenshot(path=str(screenshot_dir / 'demo-layer3-empty-dataset.png'), full_page=True)


@pytest.mark.parametrize('status', ['running', 'partial', 'failed', 'cancelled', 'interrupted'])
def test_demo_incomplete_run_and_missing_label_denominators(browser, app_server, screenshot_dir, status):
    with httpx.Client(base_url=app_server.url + '/api/v1') as client, browser.new_context() as context:
        dataset = create(client, 'Incomplete ' + status, [text_for(2, 2, n) for n in range(3)])
        run = analyze(client, dataset)
        items = client.get(f"/datasets/{dataset['id']}/items").json()['items']
        # Mutate only this test's runtime into explicit missing/error states; the
        # API still computes the counts rather than the browser inventing them.
        with sqlite3.connect(app_server.runtime / 'workspace.sqlite3') as database:
            database.execute('DELETE FROM predictions WHERE run_id=?', (run['id'],))
            database.execute('UPDATE runs SET status=? WHERE id=?', (status, run['id']))
            database.execute('UPDATE jobs SET status=?,lease_owner=NULL,lease_expires_at=NULL WHERE id=?', (status, run['job_id']))
            database.execute('UPDATE run_items SET error=? WHERE run_id=? AND item_id=?', ('Controlled test error', run['id'], items[2]['id']))
        # Topic 2: one Toxic and one missing sentiment. Topic 4: denominator zero.
        for row, labels in zip(items, [{'sentiment': 3, 'topic': 2}, {'topic': 2}, {'topic': 4}]):
            for task, label in labels.items():
                result = client.put(f"/items/{row['id']}/review", json={
                    'task': task, 'status': 'corrected', 'label_id': label,
                    'expected_revision': 1, 'expected_review_revision': 0})
                assert result.status_code == 200, result.text
        summary = client.get(f"/datasets/{dataset['id']}/summary").json()
        assert summary['attention']['eligible_count'] == 1
        assert summary['attention']['missing_sentiment_with_topic_count'] == 2
        assert summary['errors'] == 1 and summary['processed'] == 0
        page = context.new_page()
        page.goto(app_server.url + '/#/demo')
        page.locator('#dataset-select').select_option(dataset['id'])
        section = page.locator('.attention-section')
        expect(section).to_contain_text('1/3 dòng có đủ hai nhãn')
        expect(section).to_contain_text('1 dòng lỗi')
        expect(section).to_contain_text('2 dòng chưa xử lý')
        expect(section).to_contain_text('2 dòng có chủ đề nhưng thiếu cảm xúc')
        rows = section.locator('tbody tr')
        expect(rows.nth(0).locator('[data-label="Toxic"]')).to_have_text('1')
        expect(rows.nth(1).locator('[data-label="Tỷ lệ tiêu cực"]')).to_have_text('—')
        expect(rows.nth(0).locator('[data-label="Tiêu cực"]')).to_have_text('0')
        if status == 'running':
            expect(section).to_contain_text('Kết quả tạm thời')
        else:
            expect(section).to_contain_text({'partial': 'Hoàn tất một phần', 'failed': 'Có lỗi',
                                           'cancelled': 'Đã hủy', 'interrupted': 'Bị gián đoạn'}[status])
        page.screenshot(path=str(screenshot_dir / f'demo-layer3-{status}-toxic-only.png'), full_page=True)
        page.get_by_role('button', name='Chỉ dự đoán AI gốc', exact=True).click()
        expect(section).to_contain_text('0/3 dòng có đủ hai nhãn')
        expect(section).to_contain_text('3 dòng thiếu chủ đề')
        expect(section.locator('tbody tr')).to_have_count(0)
        expect(section).to_contain_text('Chưa đủ nhãn')
