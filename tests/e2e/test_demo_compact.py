"""Compact demo acceptance. API doubles exercise UI, not model quality."""
import copy
import json
from pathlib import Path
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import TestServer
from tests.e2e.test_attribution_regressions import AttributionDouble

OUTPUT = Path(__file__).resolve().parents[2] / 'test-results/demo-compact-20261112'


@pytest.fixture(scope='module')
def compact_server(tmp_path_factory):
    server = TestServer(tmp_path_factory.mktemp('compact-demo') / 'runtime', without_model=True).start()
    yield server
    server.stop()


@pytest.mark.parametrize('defect', ['missing', 'unavailable', 'schema', 'labels', 'model_schema'])
def test_neu_required_never_falls_back(browser, compact_server, defect):
    page = browser.new_page()
    double = AttributionDouble(page)
    neu = next(p for p in double.profiles if p['id'] == 'neu')
    if defect == 'missing': double.profiles = [p for p in double.profiles if p['id'] != 'neu']
    elif defect == 'unavailable': neu['model']['available'] = False
    elif defect == 'schema': neu['schema_id'] = 'uit-v1'
    elif defect == 'labels': neu['topic'].pop()
    else: neu['model']['schema_id'] = 'uit-v1'
    page.goto(compact_server.url + '/#/demo')
    page.locator('#sentence').fill('Phản hồi cần phân tích.')
    expect(page.locator('#schema-select')).to_have_count(0)
    expect(page.locator('.input-notice[role="alert"]')).to_be_visible()
    expect(page.locator('#analyze')).to_be_disabled()
    page.locator('#analysis-form').evaluate('form => form.requestSubmit()')
    assert not double.jobs
    page.close()


@pytest.mark.parametrize('width,height', [(1366,768), (1440,900), (390,844)])
def test_compact_layout_selection_scale_totals_and_zero_topics(browser, compact_server, width, height):
    page = browser.new_page(viewport=dict(width=width, height=height), reduced_motion='reduce')
    double = AttributionDouble(page, group_count=21)
    double.profiles.reverse()  # UIT comes first and is available; demo must still use NEU.
    text = 'Mình sợ môn thống kê nhưng thầy giảng rõ ràng và bạn bè hỗ trợ nên đã hiểu bài hơn nhiều.'
    assert len(text.split()) == 21
    values = [-52.2, 17.5, 1, -1, 0, 3, 4, -6, 2, 7, 0, 1, -2, 1, 1, 2, 0, 1, 1, 1, 1]
    def mutate(result):
        for group, value in zip(result['groups'], values): group['contribution'] = value
        total = sum(group['contribution'] for group in result['groups'])
        result['aggregate'].update(total_contribution=total, baseline_value=result['aggregate']['target_output']-total)
    double.mutate = mutate
    # Return zero scores in nine topics, preserving the winner and valid vector.
    def job(route):
        payload = copy.deepcopy(double.jobs[route.request.url.rsplit('/',1)[-1]])
        payload['result']['prediction']['topic']['scores'] = [1] + [0]*9
        double.jobs[payload['id']] = payload
        route.fulfill(json=payload)
    page.route('**/api/v1/jobs/*', job)
    page.goto(compact_server.url + '/#/demo')
    double.analyze(text)
    expect(page.locator('#attribution-content')).to_be_visible()
    assert next(iter(double.jobs.values()))['result']['prediction']['schema_id'] == 'neu-v1'
    expect(page.locator('.phrase-button')).to_have_count(6)
    expect(page.locator('.remaining-row')).to_contain_text('Các cụm từ còn lại (15)')
    total = page.locator('.contribution-total').inner_text()
    initial = {el.get_attribute('data-term'):el.locator('.weight-meter i').get_attribute('style')
               for el in page.locator('.phrase-button').all()}
    expect(page.locator('.score-distribution-title')).to_have_text('Phân bố điểm cảm xúc')
    expect(page.locator('#topic-scores .topic-score')).to_have_count(10)
    assert page.locator('#topic-scores .topic-score-track span').nth(1).evaluate('el => el.getBoundingClientRect().width') == 0
    for group in page.locator('.prediction-line').all():
        label, score = group.locator('strong').bounding_box(), group.locator('.prediction-percent').bounding_box()
        assert 7 <= score['x']-(label['x']+label['width']) <= 12
        assert score['y'] < label['y']+label['height']
    page.get_by_role('button', name=re.compile('Xem tất cả 21')).click()
    expect(page.locator('.phrase-button')).to_have_count(21)
    expect(page.locator('.contribution-total')).to_have_text(total)
    for term, style in initial.items():
        expect(page.locator(f'.phrase-button[data-term="{term}"] .weight-meter i')).to_have_attribute('style', style)
    ids = page.locator('.phrase-button').evaluate_all('els => els.map(el => el.dataset.term)')
    assert ids == [f'g{i}' for i in range(21)]
    hidden = next(term for term in ids if term not in initial)
    mark = page.locator(f'.word-mark[data-term="{hidden}"]')
    mark.click()
    expect(page.locator(f'.phrase-button[data-term="{hidden}"]')).to_have_attribute('aria-pressed', 'true')
    last = page.locator('.phrase-button').last
    last.focus(); page.keyboard.press('Enter')
    expect(page.locator('.word-mark').last).to_have_attribute('aria-pressed', 'true')
    if width > 760:
        columns = page.locator('.contribution-column')
        left, right = columns.nth(0).bounding_box(), columns.nth(1).bounding_box()
        assert right['x'] > left['x'] and abs(left['y']-right['y']) < 1
        assert page.locator('.phrase-button').first.bounding_box()['height'] <= 40
        assert page.locator('.topic-score-track').first.bounding_box()['width'] > 100
    else:
        boxes = page.locator('.phrase-button').evaluate_all('els => els.map(el => el.getBoundingClientRect().y)')
        assert boxes == sorted(boxes)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    page.locator('#word-analysis').screenshot(path=str(OUTPUT / f'expanded-{width}.png'))
    page.screenshot(path=str(OUTPUT / f'page-{width}.png'), full_page=True)
    height_info = dict(viewport=[width,height], expanded_section_height=page.locator('#word-analysis').bounding_box()['height'])
    (OUTPUT / f'measurements-{width}.json').write_text(json.dumps(height_info), encoding='utf-8')
    page.get_by_role('button', name='Thu gọn', exact=True).first.click()
    expect(page.locator('.phrase-button')).to_have_count(6)
    expect(page.locator('.word-mark[aria-pressed="true"]')).to_have_count(0)
    expect(page.locator('.contribution-total')).to_have_text(total)
    # Longer text must wrap and remain complete, without a nested scroll box.
    double.analyze(text + ' ' + 'Phòng học cần cải thiện. '*12)
    expect(page.locator('#attribution-content')).to_be_visible()
    page.get_by_role('button', name=re.compile('Xem tất cả')).click()
    expect(page.locator('.quote-text')).to_have_text((text + ' ' + 'Phòng học cần cải thiện. '*12).strip())
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#word-analysis').screenshot(path=str(OUTPUT / f'long-{width}.png'))
    page.close()


@pytest.mark.parametrize('progress,expected', [({},None), ({'completed_batches':0,'total_batches':0},None),
    ({'completed_batches':-1,'total_batches':10},None), ({'completed_batches':11,'total_batches':10},None),
    ({'completed_batches':2.5,'total_batches':10},None), ({'completed_batches':2,'total_batches':8},'25'),
    ({'completed_batches':8,'total_batches':8},'100')])
def test_true_attribution_progress_only_and_reset(browser, compact_server, progress, expected):
    page = browser.new_page(reduced_motion='reduce')
    double = AttributionDouble(page)
    double.get_status = 'running'
    page.route('**/api/v1/attributions/*', lambda route: route.fulfill(json=dict(attribution_id='attr1', status='running',
        groups=[], progress=progress)))
    page.goto(compact_server.url + '/#/demo')
    double.analyze()
    bar = page.get_by_role('progressbar', name='Tiến độ tính đóng góp', exact=True)
    expect(bar).to_be_visible()
    if expected is None: expect(bar).not_to_have_attribute('aria-valuenow')
    else: expect(bar).to_have_attribute('aria-valuenow', expected)
    if expected == '100': expect(page.locator('.analysis-progress-status')).to_have_text('Đang hoàn tất kết quả…')
    expect(page.locator('#attribution-content')).to_have_count(0)
    expect(page.locator('#sentiment')).to_be_visible()
    expect(page.get_by_role('progressbar')).to_have_count(1)
    if expected == '25': page.locator('#analysis').screenshot(path=str(OUTPUT / 'progress-25.png'))
    page.locator('#sentence').fill('Nội dung mới bỏ tiến độ cũ.')
    expect(page.get_by_role('progressbar')).to_have_count(0)
    page.close()


def test_progress_real_stages_validation_and_cancel_race(browser, compact_server):
    page = browser.new_page()
    double = AttributionDouble(page)
    stage = ['queued']
    page.route('**/api/v1/jobs/*', lambda route: route.fulfill(json=dict(
        double.jobs[route.request.url.rsplit('/',1)[-1]], status=stage[0])))
    page.add_init_script('''const digest = crypto.subtle.digest.bind(crypto.subtle);
      crypto.subtle.digest = async (...args) => { await new Promise(resolve => { window.releaseDigest = resolve; }); return digest(...args); };''')
    page.goto(compact_server.url + '/#/demo')
    page.locator('#sentence').fill('Giữ kết quả khi xác thực và hủy.')
    page.locator('#analyze').click()
    expect(page.locator('.analysis-progress-status')).to_have_text('Đang chờ xử lý…')
    expect(page.get_by_role('progressbar')).not_to_have_attribute('aria-valuenow')
    stage[0] = 'loading_model'
    expect(page.locator('.analysis-progress-status')).to_have_text('Đang nạp model…')
    stage[0] = 'running'
    expect(page.locator('.analysis-progress-status')).to_have_text('Đang phân tích cảm xúc và chủ đề…')
    stage[0] = 'completed'
    expect(page.locator('#sentiment')).to_be_visible()
    expect(page.locator('.analysis-progress-status')).to_have_text('Đang hoàn tất kết quả…')
    expect(page.locator('#attribution-content')).to_have_count(0)
    page.get_by_role('button', name='Hủy tính toán').click()
    page.evaluate('window.releaseDigest()')
    expect(page.get_by_role('progressbar')).to_have_count(0)
    expect(page.locator('#attribution-content')).to_have_count(0)
    expect(page.locator('#sentiment')).to_be_visible()
    page.get_by_role('button', name='Thử lại tính đóng góp').click()
    expect(page.get_by_role('progressbar')).to_be_visible()
    page.wait_for_function('window.releaseDigest !== undefined')
    page.evaluate('window.releaseDigest()')
    expect(page.locator('#attribution-content')).to_be_visible()
    expect(page.get_by_role('progressbar')).to_have_count(0)
    page.close()

@pytest.mark.parametrize('width,touch', [(1366,False),(1440,False),(390,True)])
def test_long_topic_phrase_and_touch_targets(browser, compact_server, width, touch):
    page = browser.new_page(viewport=dict(width=width,height=900), has_touch=touch, device_scale_factor=1)
    double = AttributionDouble(page)
    def job(route):
        payload = copy.deepcopy(double.jobs[route.request.url.rsplit('/',1)[-1]])
        payload['result']['prediction']['topic'] = dict(label_id=9, scores=[0]*9+[1])
        double.jobs[payload['id']] = payload
        route.fulfill(json=payload)
    page.route('**/api/v1/jobs/*', job)
    page.goto(compact_server.url + '/#/demo')
    double.analyze('Cụm từ dài để kiểm tra xuống dòng và giữ nguyên nội dung. '*5)
    expect(page.locator('#attribution-content')).to_be_visible()
    expect(page.locator('#topic')).to_have_text('Câu lạc bộ / sự kiện')
    assert page.locator('.prediction-headlines').evaluate('el => el.scrollWidth <= el.clientWidth')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('.phrase-text').inner_text() == next(iter(double.jobs.values()))['result']['text']
    if touch:
        for selector in ['.phrase-button', '.word-mark', '.method-details summary']:
            assert page.locator(selector).first.bounding_box()['height'] >= 44
    page.locator('#analysis').screenshot(path=str(OUTPUT / f'long-topic-{width}.png'))
    page.close()


def test_sending_request_has_no_invented_percentage_or_queued_stage(browser, compact_server):
    page = browser.new_page()
    double = AttributionDouble(page)
    double.hold_next = True
    page.goto(compact_server.url + '/#/demo')
    double.analyze()
    expect(page.locator('.analysis-progress-status')).to_have_text('Đang gửi yêu cầu tính đóng góp…')
    expect(page.get_by_role('progressbar')).not_to_have_attribute('aria-valuenow')
    route, result = double.held.pop()
    route.fulfill(json=result)
    expect(page.locator('#attribution-content')).to_be_visible()
    page.close()


def test_retry_disabled_if_neu_becomes_unavailable(browser, compact_server):
    page = browser.new_page()
    page.clock.install()
    double = AttributionDouble(page)
    page.route('**/api/v1/jobs/*', lambda route: route.fulfill(json=dict(
        double.jobs[route.request.url.rsplit('/',1)[-1]], status='failed', result=None)))
    page.goto(compact_server.url + '/#/demo')
    page.locator('#sentence').fill('Câu thử lại cần model NEU sẵn sàng.')
    page.locator('#analyze').click()
    retry = page.get_by_role('button', name='Chạy lại tác vụ này')
    expect(retry).to_be_enabled()
    next(p for p in double.profiles if p['id'] == 'neu')['model']['available'] = False
    page.clock.fast_forward(15001)
    expect(page.locator('.input-notice')).to_contain_text('Model NEU chưa sẵn sàng')
    expect(retry).to_be_disabled()
    expect(page.locator('#analyze')).to_be_disabled()
    page.close()
