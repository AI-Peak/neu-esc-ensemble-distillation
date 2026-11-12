"""Explicit opt-in real browser acceptance against this session's isolated preview stack."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

import httpx
import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.mark.real_model
def test_real_prediction_attribution_browser_and_dataset_snapshot():
    base=os.environ['FEEDBACK_FIX_APP_URL']
    runtime=Path(os.environ['FEEDBACK_FIX_RUNTIME']).resolve()
    output=Path(os.environ['FEEDBACK_FIX_EVIDENCE']).resolve(); output.mkdir(parents=True,exist_ok=True)
    health=httpx.get(base+'/api/v1/health').json()
    assert Path(health['runtime']).resolve()==runtime and health['worker']['alive'] and health['database_version']==4
    assert 'test-results' in runtime.parts
    results=[];page_errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        page=browser.new_page(viewport=dict(width=1440,height=1000),reduced_motion='reduce')
        page.on('pageerror',lambda error:page_errors.append(str(error)))
        def analyze(text,label):
            page.goto(base+'/#/demo')
            page.locator('#sentence').fill(text)
            start=time.perf_counter()
            with page.expect_response(lambda r:r.url.endswith('/quick-analysis') and r.request.method=='POST') as quick:
                page.locator('#analyze').click()
            job_id=quick.value.json()['job_id']
            expect(page.locator('#result-content')).to_be_visible(timeout=60000)
            prediction_elapsed=time.perf_counter()-start
            expect(page.locator('.attribution-table')).to_be_visible(timeout=60000)
            job=httpx.get(base+'/api/v1/jobs/'+job_id).json()
            expect(page.locator('#contribution-donut')).to_be_visible(timeout=10000)
            expect(page.locator('#evidence-list .evidence-row')).to_have_count(1)
            expect(page.locator('#evidence-list .evidence-text p')).to_have_text(text)
            expect(page.locator('#dataset-select')).to_have_count(0)
            expect(page.locator('.quick-add-box')).to_have_count(0)
            # Locate the completed handle via response snapshot already verified by the UI.
            with sqlite3.connect(runtime/'workspace.sqlite3') as db:
                attr_id=db.execute("SELECT id FROM attribution_jobs WHERE source_job_id=? AND status='completed' ORDER BY created_at DESC LIMIT 1",(job_id,)).fetchone()[0]
            result=httpx.get(base+'/api/v1/attributions/'+attr_id).json()
            assert result['status']=='completed'
            item=job['result'];pred=item['prediction'];source=result['source']
            assert source['execution_identity']==pred['execution_identity']
            assert source['text_hash']==hashlib.sha256(item['text'].encode()).hexdigest()
            assert source['model_id']!='TEST-DOUBLE-NOT-A-MODEL'
            assert abs(sum(g['contribution'] for g in result['groups'])-result['aggregate']['total_contribution'])<=1e-6
            first=page.locator('.word-mark').first
            first.click();expect(first).to_have_attribute('aria-pressed','true')
            group_id=first.get_attribute('data-term')
            expect(page.locator('.phrase-button[data-term="'+group_id+'"]')).to_have_attribute('aria-pressed','true')
            phrase=page.locator('.phrase-button').last;phrase.focus();page.keyboard.press('Enter')
            expect(phrase).to_have_attribute('aria-pressed','true')
            expect(page.locator('.method-details')).not_to_have_attribute('open','')
            page.locator('.method-details summary').click()
            expect(page.locator('.method-details')).to_have_attribute('open','')
            page.locator('.method-details summary').click()
            typography=page.locator('.sentence-demo-root').evaluate("el => ({family:getComputedStyle(el).fontFamily,synthesis:getComputedStyle(el).fontSynthesis})")
            if page.locator('.word-mark.negative-mark').count():
                typography['negative_style']=page.locator('.word-mark.negative-mark').first.evaluate("el => getComputedStyle(el).fontStyle")
            results.append(dict(label=label,text=text,job_id=job_id,attribution=result,prediction=pred,typography=typography,
                seconds_to_prediction=prediction_elapsed,seconds_to_table=time.perf_counter()-start))
            (output/'real-browser-partial.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            return result
        analyze('Thư viện sáng sủa nhưng wifi mất kết nối mỗi buổi chiều.','mixed-neutral')
        for width in (320,390,768,1440,1920):
            page.set_viewport_size(dict(width=width,height=1000))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('#word-analysis').screenshot(path=str(output/f'real-table-{width}-collapsed.png'))
        page.set_viewport_size(dict(width=1440,height=1000))
        page.screenshot(path=str(output/'real-page-desktop.png'),full_page=True)
        if page.get_by_role('button',name='Xem đủ',exact=True).count():
            page.get_by_role('button',name='Xem đủ',exact=True).click()
            page.locator('#word-analysis').screenshot(path=str(output/'real-table-1440-expanded.png'))
            page.set_viewport_size(dict(width=390,height=1000))
            page.locator('#word-analysis').screenshot(path=str(output/'real-table-390-expanded.png'))
            page.screenshot(path=str(output/'real-page-mobile.png'),full_page=True)
        page.set_viewport_size(dict(width=1440,height=1000))
        analyze('Máy chiếu nhòe và điều hòa phòng học không hoạt động.','negative')
        page.locator('#word-analysis').screenshot(path=str(output/'real-negative.png'))
        analyze('Dịch vụ tốt nhưng thời gian chờ quá lâu.','mixed-polarity')
        page.locator('#word-analysis').screenshot(path=str(output/'real-polarity-1440.png'))
        page.set_viewport_size(dict(width=390,height=1000))
        page.locator('#word-analysis').screenshot(path=str(output/'real-polarity-390.png'))
        page.set_viewport_size(dict(width=1440,height=1000))
        analyze('Địt mẹ cái trường lồn này, làm ăn như cứt.','intended-toxic')
        page.locator('#word-analysis').screenshot(path=str(output/'real-intended-toxic.png'))
        # Actual source and model remain real while a pending attribution POST is held
        # briefly to observe the loading UI, then delivered unchanged.
        held=[]
        page.route('**/quick-analysis/*/attribution',lambda route:held.append(route))
        page.locator('#sentence').fill('Cô hướng dẫn hồ sơ tận tình, nhưng trang đăng ký thường bị lỗi.')
        page.locator('#analyze').click()
        expect(page.get_by_role('button',name='Hủy tính toán')).to_be_visible(timeout=60000)
        page.locator('#word-analysis').screenshot(path=str(output/'real-prediction-loading-attribution.png'))
        assert held
        held[0].continue_();page.unroute('**/quick-analysis/*/attribution')
        expect(page.locator('.attribution-table')).to_be_visible(timeout=60000)
        # Real unsupported truncation.
        page.locator('#sentence').fill('Thư viện có tài liệu mới. '*55)
        page.locator('#analyze').click()
        expect(page.locator('#word-analysis .notice.error')).to_contain_text('giới hạn token',timeout=60000)
        expect(page.locator('#sentiment')).to_be_visible()
        page.locator('#word-analysis').screenshot(path=str(output/'real-unsupported-truncation.png'))
        # Expire only a session-owned quick source while GET is pending: HTTP410
        # must stop polling and preserve the already-visible real prediction.
        held_get=[]
        page.route('**/attributions/*',lambda route:held_get.append(route) if route.request.method=='GET' else route.continue_())
        page.locator('#sentence').fill('Tài liệu học tập rõ ràng nhưng đường dẫn thường hỏng.')
        with page.expect_response(lambda r:r.url.endswith('/quick-analysis') and r.request.method=='POST') as quick:
            page.locator('#analyze').click()
        job_id=quick.value.json()['job_id']
        expect(page.get_by_role('button',name='Hủy tính toán')).to_be_visible(timeout=60000)
        for _ in range(100):
            if held_get:break
            page.wait_for_timeout(50)
        assert held_get
        with sqlite3.connect(runtime/'workspace.sqlite3') as db:
            db.execute('UPDATE datasets SET expires_at=? WHERE id=(SELECT dataset_id FROM runs WHERE id=(SELECT run_id FROM jobs WHERE id=?))',(time.time()-1,job_id));db.commit()
        held_get[0].continue_()
        expect(page.locator('#word-analysis .notice.error')).to_contain_text('hết hạn',timeout=10000)
        expect(page.locator('#sentiment')).to_be_visible()
        page.locator('#word-analysis').screenshot(path=str(output/'real-source-expired-error.png'))
        count=len(held_get);page.wait_for_timeout(1800);assert len(held_get)==count
        page.unroute('**/attributions/*')
        # The graph follows the latest quick sentence, without creating durable fixtures.
        latest_text='Thư viện rộng rãi, phòng đọc yên tĩnh và bàn ghế sạch sẽ.'
        analyze(latest_text,'latest-sentence-network')
        latest=httpx.get(base+'/api/v1/jobs/'+results[-1]['job_id']).json()
        page.locator('#network').scroll_into_view_if_needed()
        expect(page.locator('#term-network .graph-node').first).to_be_visible(timeout=30000)
        graph=httpx.get(base+'/api/v1/datasets/'+latest['result']['dataset_id']+'/network',
            params=dict(label_source='ai',run_id=latest['run_id'])).json()
        assert graph['status']=='completed' and graph['source_item_count']==graph['scope_item_count']==1
        assert all(node['item_ids']==[latest['result']['id']] for node in graph['nodes'])
        assert all(node['id']!='wifi' for node in graph['nodes'])
        page.locator('#network').screenshot(path=str(output/'real-network-desktop.png'))
        page.locator('#term-network .graph-node').first.focus();page.keyboard.press('Enter')
        page.locator('#show-node-evidence').click()
        expect(page.locator('#evidence-list article').first).to_be_visible()
        expect(page.locator('#evidence-list .evidence-text p')).to_have_text(latest_text)
        page.locator('#evidence').screenshot(path=str(output/'real-network-evidence.png'))
        for width in (390,320):
            page.set_viewport_size(dict(width=width,height=1000))
            page.locator('#network').screenshot(path=str(output/('real-network-mobile.png' if width==390 else 'real-network-320.png')))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            key=page.locator('.graph-key').bounding_box()
            picker=page.locator('.mobile-term-picker').bounding_box()
            assert key and picker and key['y']+key['height']<=picker['y'], (key,picker)
        assert not page_errors,page_errors
        (output/'real-browser-evidence.json').write_text(json.dumps(dict(url=base,runtime=str(runtime),
            kind='REAL_CHECKPOINT_OFFLINE',results=results,health=health,network=graph,
            dataset_id=latest['result']['dataset_id'],page_errors=page_errors),ensure_ascii=False,indent=2),encoding='utf-8')
        browser.close()
