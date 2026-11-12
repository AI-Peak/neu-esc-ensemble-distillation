"""Contribution semantics with API doubles; these are not checkpoint evidence."""
import math
import re
import json

import pytest
from playwright.sync_api import expect

from tests.e2e.test_attribution_regressions import AttributionDouble
from tests.e2e.conftest import TestServer


@pytest.fixture(scope='module')
def contribution_server(tmp_path_factory):
    # All API calls are intercepted per page. Reuse only the static app server;
    # this fixture has no model or cross-test prediction state.
    server = TestServer(tmp_path_factory.mktemp('contribution-ui')/'runtime', without_model=True).start()
    yield server
    server.stop()


def assert_shares(page, values):
    p = math.fsum(max(value, 0) for value in values)
    n = math.fsum(max(-value, 0) for value in values)
    scale = max(map(abs, values))
    # Avoid underflow in test arithmetic too (e.g. the smallest JS subnormal).
    positive = math.fsum(max(value / scale, 0) for value in values) if scale else 0
    negative = math.fsum(max(-value / scale, 0) for value in values) if scale else 0
    if not scale:
        expect(page.locator('.distribution-pane')).to_contain_text('Chưa có đóng góp khác 0')
        expect(page.locator('#contribution-donut')).to_have_count(0)
        return
    expected = positive / (positive + negative)
    tenths = math.floor(expected * 1000 + .5)
    expect(page.locator('#contribution-legend strong')).to_have_text([
        f'{tenths/10:.1f}%'.replace('.', ','), f'{(1000-tenths)/10:.1f}%'.replace('.', ',')])
    for direction, fraction in [('increase', expected), ('decrease', negative / (positive + negative))]:
        circle = page.locator(f'#contribution-donut [data-direction="{direction}"]')
        if fraction == 0:
            expect(circle).to_have_count(0)
        else:
            expect(circle).to_have_count(1)
            dash = float(circle.get_attribute('stroke-dasharray').split()[0])
            assert math.isfinite(dash) and math.isclose(dash / (2*math.pi*86), fraction, abs_tol=1e-14)
    assert p >= 0 and n >= 0


@pytest.mark.parametrize('values', [
    [30, 10, -80, -40], [30, 10], [-80, -40], [30, -30], [0, 0],
    [30, 10, -80, -40, 3, -7, 1, -2, 5],
    [.1, .2, -.4], [1e-300, -3e-300], [5e-324, -5e-324],
    [1e-12, -1], [1e308, -1e308],
])
def test_mass_formula_all_groups_and_display_rounding(browser, contribution_server, values):
    page = browser.new_page()
    double = AttributionDouble(page, winner=2, group_count=len(values))
    def mutate(result):
        for group, value in zip(result['groups'], values):
            group['contribution'] = value
        total = sum(values)
        result['aggregate'].update(total_contribution=total,
            baseline_value=result['aggregate']['target_output']-total,
            hidden_groups_contribution=12345)  # Display aggregates never enter P/N.
    double.mutate = mutate
    page.goto(contribution_server.url + '/#/demo')
    double.analyze(' '.join(f'cụm{i}' for i in range(len(values))))
    expect(page.locator('.attribution-table')).to_be_visible()
    assert_shares(page, values)
    if len(values) > 6:
        expect(page.locator('.remaining-row')).to_be_visible()
        page.get_by_role('button', name='Xem đủ', exact=True).click()
        assert_shares(page, values)
        page.get_by_role('button', name='Thu gọn lại 6 từ chính').click()
        assert_shares(page, values)
    if values == [30, 10, -80, -40]:
        expect(page.locator('.total-sign')).to_have_text('−80,0')
    if values == [1e-12, -1]:
        expect(page.locator('#contribution-legend')).to_contain_text('Dưới 0,05% trước làm tròn')
    assert len(double.jobs) == len(double.posts) == 1
    page.close()


@pytest.mark.parametrize('invalid', ['NaN', '1e999', '-1e999'])
def test_nonfinite_never_renders_chart_or_table(browser, contribution_server, invalid):
    page = browser.new_page()
    double = AttributionDouble(page)
    def malformed_response(route):
        job_id = route.request.url.split('/quick-analysis/')[1].split('/')[0]
        result = double.completed('invalid-number', job_id, route.request.post_data_json['target'])
        result['groups'][0]['contribution'] = 'NONFINITE'
        # Send raw bytes, not a nonfinite value through Playwright's own JSON
        # protocol. Exponent overflow is valid JSON and reaches the validator;
        # NaN is invalid JSON and must fail parsing without rendering a chart.
        body = json.dumps(result).replace('"NONFINITE"', invalid)
        route.fulfill(status=200, content_type='application/json', body=body)
    page.route('**/quick-analysis/*/attribution', malformed_response)
    page.goto(contribution_server.url + '/#/demo')
    double.analyze()
    expect(page.locator('#word-analysis .notice.error')).to_be_visible()
    expect(page.locator('.attribution-table, #contribution-donut')).to_have_count(0)
    expect(page.locator('#sentiment')).to_be_visible()
    expect(page.locator('.distribution-pane [role="status"]')).to_be_visible()
    page.close()


@pytest.mark.parametrize('profile,winner,reorder', [('neu',1,False), ('neu',0,False),
    ('neu',3,False), ('uit',1,False), ('uit',0,False), ('neu',1,True), ('neu',0,True)])
def test_target_labels_colors_accessibility_and_no_filter(browser, contribution_server, profile, winner, reorder):
    page = browser.new_page()
    double = AttributionDouble(page, profile=profile, winner=winner)
    if reorder:
        prof = next(p for p in double.profiles if p['id'] == profile)
        prof['sentiment'][1], prof['sentiment'][3] = prof['sentiment'][3], prof['sentiment'][1]
        # A schema whose Toxic class is index/id1 and Positive is index/id3.
        # The double's label IDs, winner and score order remain consistent.
        for index, label in enumerate(prof['sentiment']):
            label['id'] = index
    page.goto(contribution_server.url + '/#/demo')
    if profile != 'neu': page.locator('#schema-select').select_option(profile)
    double.analyze()
    expect(page.locator('#contribution-donut')).to_be_visible()
    result = next(iter(double.results.values()))
    prof = next(p for p in double.profiles if p['id'] == profile)
    target = result['method']['target']
    if target['kind'] == 'polarity_margin':
        labels, colors = ['Nghiêng tích cực', 'Nghiêng tiêu cực'], ['#39996a', '#c76b5d']
    else:
        name = next(l['name'] for l in prof['sentiment'] if l['id'] == target['label_id'])
        labels, colors = [f'Tăng điểm {name}', f'Giảm điểm {name}'], ['#417caa', '#b45309']
        expect(page.locator('.distribution-pane')).not_to_contain_text('Nghiêng tích cực')
    expect(page.locator('#contribution-legend li > span')).to_have_text(labels)
    circle = page.locator('#contribution-donut circle').first
    for direction, color in zip(['increase', 'decrease'], colors):
        rgb = 'rgb(' + ', '.join(str(int(color[i:i+2], 16)) for i in (1, 3, 5)) + ')'
        assert page.locator(f'#contribution-legend [data-direction="{direction}"] .dot').evaluate('el => el.style.backgroundColor') == rgb
        segment = page.locator(f'#contribution-donut [data-direction="{direction}"]')
        if segment.count(): expect(segment).to_have_attribute('stroke', color)
    expect(page.locator('#contribution-donut')).to_have_attribute('role', 'img')
    expect(page.locator('#contribution-donut desc')).to_contain_text(labels[0])
    expect(page.locator('.distribution-pane [role="button"], .distribution-pane button, .distribution-pane [tabindex], .distribution-pane [aria-pressed]')).to_have_count(0)
    expect(page.locator('.distribution-pane')).not_to_contain_text(re.compile('Net sentiment|phản hồi|có nhãn'))
    page.locator('#contribution-legend li').first.click()
    expect(page.locator('#active-filters')).to_have_count(0)
    assert circle.evaluate('el => getComputedStyle(el).cursor') != 'pointer'
    assert len(double.jobs) == len(double.posts) == 1
    page.close()
