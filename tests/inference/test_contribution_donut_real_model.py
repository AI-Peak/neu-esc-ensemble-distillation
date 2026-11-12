"""Opt-in, offline checkpoint browser evidence. Requires an isolated test-results stack."""
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

from tests.e2e.test_contribution_donut import assert_shares


SUPERMARKET = ('Kể từ khi một người quản lý mới tiếp quản, siêu thị từng được coi là tốt nhất quanh đây này đã sa sút thảm hại. '
    'Họ hầu như không có gì cả, rau củ quả thì luôn hết hạn/hỏng, và cửa hàng không được duy trì/chăm chút cẩn thận. '
    'Được cái là nhân viên dễ thương')


@pytest.mark.real_model
def test_contribution_donut_real_checkpoint():
    base = os.environ['FEEDBACK_FIX_APP_URL']
    runtime = Path(os.environ['FEEDBACK_FIX_RUNTIME']).resolve()
    output = Path(os.environ['FEEDBACK_FIX_EVIDENCE']).resolve()
    output.mkdir(parents=True, exist_ok=True)
    assert 'test-results' in runtime.parts
    health = httpx.get(base + '/api/v1/health').json()
    assert Path(health['runtime']).resolve() == runtime and health['worker']['alive']
    profiles = httpx.get(base + '/api/v1/profiles').json()
    profile = next(p for p in profiles if p['id'] == 'neu')
    assert not next(p for p in profiles if p['id'] == 'uit')['model']['available']
    results, errors, requests = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=dict(width=1440, height=1000), reduced_motion='reduce')
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(dict(url=request.url, method=request.method)))
        page.goto(base + '/#/demo')
        expect(page.locator('#contribution-donut')).to_have_count(0)
        for name, text in [('supermarket', SUPERMARKET),
            ('service', 'Dịch vụ tốt nhưng thời gian chờ quá lâu.'),
            ('library', 'Thư viện sáng sủa nhưng wifi mất kết nối mỗi buổi chiều.'),
            ('toxic', 'Địt mẹ cái trường lồn này, làm ăn như cứt.')]:
            print('REAL_CONTRIBUTION', name, flush=True)
            page.locator('#sentence').fill(text)
            expect(page.locator('#contribution-donut')).to_have_count(0)
            with page.expect_response(lambda r: r.url.endswith('/quick-analysis') and r.request.method == 'POST') as created:
                page.locator('#analyze').click()
            job_id = created.value.json()['job_id']
            expect(page.locator('#result-content')).to_be_visible(timeout=60000)
            expect(page.locator('.attribution-table')).to_be_visible(timeout=60000)
            expect(page.locator('#contribution-donut')).to_be_visible()
            item = httpx.get(base + '/api/v1/jobs/' + job_id).json()['result']
            attr_id = page.locator('.contribution-layout').get_attribute('data-attribution-id')
            attr = httpx.get(base + '/api/v1/attributions/' + attr_id).json()
            assert attr['status'] == 'completed'
            assert attr['source']['source_prediction_id'] == item['prediction']['id']
            assert attr['source']['execution_identity'] == item['prediction']['execution_identity']
            assert attr['source']['text_hash'] == hashlib.sha256(text.encode()).hexdigest()
            assert attr['source']['model_id'] != 'TEST-DOUBLE-NOT-A-MODEL'
            values = [g['contribution'] for g in attr['groups']]
            p = math.fsum(max(v, 0) for v in values)
            n = math.fsum(max(-v, 0) for v in values)
            assert abs((p-n)-attr['aggregate']['total_contribution']) <= 1e-6
            assert_shares(page, values)
            target = attr['method']['target']
            if target['kind'] == 'polarity_margin': labels = ['Nghiêng tích cực', 'Nghiêng tiêu cực']
            else:
                label = next(l['name'] for l in profile['sentiment'] if l['id'] == target['label_id'])
                labels = [f'Tăng điểm {label}', f'Giảm điểm {label}']
            expect(page.locator('#contribution-legend li > span')).to_have_text(labels)
            if name == 'toxic':
                actual_label = next(l for l in profile['sentiment'] if l['id'] == item['prediction']['sentiment']['label_id'])
                assert actual_label['key'].casefold() == 'toxic', actual_label
                assert target['kind'] == 'label_score'
            record = dict(name=name, text=text, item=item, attribution=attr, P=p, N=n, M=p+n, D=p-n,
                increase_percent=100*p/(p+n), decrease_percent=100*n/(p+n),
                displayed=page.locator('#contribution-legend strong').all_text_contents())
            results.append(record)
            (output/'real-contribution-partial.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            before = page.locator('#contribution-legend').text_content()
            if page.get_by_role('button', name='Xem đủ', exact=True).count():
                page.get_by_role('button', name='Xem đủ', exact=True).click()
                expect(page.locator('#contribution-legend')).to_have_text(before)
                page.get_by_role('button', name='Thu gọn lại 6 từ chính').click()
            page.locator('.word-mark').first.click()
            group = page.locator('.word-mark').first.get_attribute('data-term')
            expect(page.locator(f'.phrase-button[data-term="{group}"]')).to_have_attribute('aria-pressed', 'true')
            page.locator('.phrase-button').last.focus()
            page.keyboard.press('Enter')
            expect(page.locator('.phrase-button').last).to_have_attribute('aria-pressed', 'true')
            page.locator('.phrase-button').last.evaluate('el => el.blur()')
            for width in (1440, 390, 320, 768):
                page.set_viewport_size(dict(width=width, height=1000))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, width)
                assert page.locator('.distribution-pane').evaluate('(el) => el.scrollWidth <= el.clientWidth')
                legend_boxes = [page.locator('#contribution-legend li').nth(i).bounding_box() for i in (0, 1)]
                if abs(legend_boxes[0]['y'] - legend_boxes[1]['y']) < 1:
                    assert legend_boxes[1]['x'] - (legend_boxes[0]['x'] + legend_boxes[0]['width']) >= 16
                page.locator('#overview').screenshot(path=str(output/f'real-{name}-overview-{width}.png'))
                if width in (1440, 390):
                    page.locator('#word-analysis').screenshot(path=str(output/f'real-{name}-table-{width}.png'))
                assert_shares(page, values)
            if name == 'supermarket':
                page.set_viewport_size(dict(width=390, height=1000))
                page.evaluate('window.scrollTo(0, 0)')
                page.screenshot(path=str(output/'real-supermarket-page-mobile.png'), full_page=True)
                page.set_viewport_size(dict(width=1440, height=1000))
                page.evaluate('window.scrollTo(0, 0)')
                page.screenshot(path=str(output/'real-supermarket-page-desktop.png'), full_page=True)
            page.set_viewport_size(dict(width=1440, height=1000))

        # Preserve real prediction while the unchanged attribution POST is held.
        held = []
        page.route('**/quick-analysis/*/attribution', lambda route: held.append(route))
        page.locator('#sentence').fill('Cô hướng dẫn hồ sơ tận tình, nhưng trang đăng ký thường bị lỗi.')
        page.locator('#analyze').click()
        expect(page.get_by_role('button', name='Hủy tính toán')).to_be_visible(timeout=60000)
        expect(page.locator('#contribution-donut')).to_have_count(0)
        expect(page.locator('.distribution-pane')).to_contain_text('Đang tính tỷ trọng')
        expect(page.locator('#sentiment')).to_be_visible()
        page.locator('#overview').screenshot(path=str(output/'real-loading.png'))
        assert held
        held[0].continue_()
        page.unroute('**/quick-analysis/*/attribution')
        expect(page.locator('#contribution-donut')).to_be_visible(timeout=60000)

        page.locator('#sentence').fill('Thư viện có tài liệu mới. '*55)
        expect(page.locator('#contribution-donut')).to_have_count(0)
        page.locator('#analyze').click()
        expect(page.locator('#word-analysis .notice.error')).to_contain_text('giới hạn token', timeout=60000)
        expect(page.locator('.distribution-pane')).to_contain_text('giới hạn token')
        expect(page.locator('#contribution-donut')).to_have_count(0)
        expect(page.locator('#sentiment')).to_be_visible()
        page.locator('#overview').screenshot(path=str(output/'real-unsupported.png'))

        # Expire ONLY this test's own source while a real poll is pending.
        held_get = []
        page.route('**/attributions/*', lambda route: held_get.append(route) if route.request.method == 'GET' else route.continue_())
        page.locator('#sentence').fill('Tài liệu học tập rõ ràng nhưng đường dẫn thường hỏng.')
        with page.expect_response(lambda r: r.url.endswith('/quick-analysis') and r.request.method == 'POST') as created:
            page.locator('#analyze').click()
        job_id = created.value.json()['job_id']
        expect(page.get_by_role('button', name='Hủy tính toán')).to_be_visible(timeout=60000)
        for _ in range(100):
            if held_get: break
            page.wait_for_timeout(50)
        assert held_get
        import time
        with sqlite3.connect(runtime/'workspace.sqlite3') as db:
            db.execute('UPDATE datasets SET expires_at=? WHERE id=(SELECT dataset_id FROM runs WHERE id=(SELECT run_id FROM jobs WHERE id=?))', (time.time()-1, job_id))
            db.commit()
        held_get[0].continue_()
        expect(page.locator('.distribution-pane')).to_contain_text('hết hạn', timeout=10000)
        expect(page.locator('#contribution-donut')).to_have_count(0)
        expect(page.locator('#sentiment')).to_be_visible()
        page.locator('#overview').screenshot(path=str(output/'real-source-410.png'))
        count = len(held_get)
        page.wait_for_timeout(1600)
        assert len(held_get) == count
        assert not errors, errors
        # Four completed examples + loading example + truncation + expired source.
        assert len([r for r in requests if r['method'] == 'POST' and r['url'].endswith('/quick-analysis')]) == 7
        assert len([r for r in requests if r['method'] == 'POST' and r['url'].endswith('/attribution')]) == 7
        (output/'real-contribution-evidence.json').write_text(json.dumps(dict(kind='REAL_CHECKPOINT_OFFLINE',
            url=base, runtime=str(runtime), health=health, results=results, page_errors=errors, requests=requests), ensure_ascii=False, indent=2), encoding='utf-8')
        browser.close()
