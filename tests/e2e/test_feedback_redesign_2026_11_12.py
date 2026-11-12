from __future__ import annotations

import os
from pathlib import Path
import httpx
from playwright.sync_api import expect, Page
from tests.e2e.test_contribution_donut import assert_shares

ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_DIR = Path(
    os.environ.get("SENTENCE_DEMO_SCREENSHOT_DIR")
    or (ROOT / "artifacts" / "screenshots_2026_11_12")
)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def analyze_latest(page: Page, server_url: str, text: str):
    """Submit through the UI and return the actual server-owned quick snapshot."""
    page.locator("#sentence").fill(text)
    with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/api/v1/quick-analysis")) as pending:
        page.locator("#analyze").click()
    created = pending.value.json()
    # Replacing A can queue B behind A's non-interruptible cold NLP setup.
    # Source/snapshot assertions below must wait for B, without a 15-second SLA.
    expect(page.locator("#result-content")).to_be_visible(timeout=60000)
    result = httpx.get(f"{server_url}/api/v1/jobs/{created['job_id']}").json()
    assert result["status"] == "completed", result
    item = result["result"]
    assert item["text"] == text.strip()
    return item


def negative_double_sentence(base: str):
    # The software registry uses this score rule. It is only a test input choice,
    # never a claim that the trained checkpoint must classify this sentence negative.
    for index in range(100):
        text = f"{base} Kiểm thử {index}."
        if sum(map(ord, text)) % 4 == 2:
            return text
    raise AssertionError("Could not construct deterministic Negative software fixture")


# ============================================================================
# R01 & R02: Không có nút câu mẫu, không có boilerplate thừa, không có nhãn Lớp 1/2/3
# ============================================================================
def test_r01_r02_clean_input_and_no_layer_tags(browser, demo_server):
    page: Page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(demo_server.url + "/#/demo")

    # R01: Verify 3 sample sentence buttons are completely removed
    sample_buttons = page.locator("button.example")
    expect(sample_buttons).to_have_count(0)
    expect(page.locator("text='Thử nhanh với một câu mẫu'")).to_have_count(0)

    # R01: Verify redundant sentence "Văn bản gốc luôn được giữ nguyên" is removed
    expect(page.locator("text='Văn bản gốc luôn được giữ nguyên'")).to_have_count(0)

    # R01: Character counter is still present
    char_count = page.locator("#character-count")
    expect(char_count).to_be_visible()
    expect(char_count).to_contain_text("0 / 5.000 ký tự")

    # R02: Verify layer tags Lớp 1/2/3 are removed
    expect(page.locator("text='Lớp 1 · Prediction'")).to_have_count(0)
    expect(page.locator("text='Lớp 2 · Interpretability'")).to_have_count(0)
    expect(page.locator("text='Lớp 3 · Decision Support'")).to_have_count(0)

    page.screenshot(path=str(SCREENSHOT_DIR / "r01_r02_clean_input_header.png"))
    page.close()


# ============================================================================
# R03: Giữ nguyên văn phản hồi và kết quả prediction local
# ============================================================================
def test_r03_local_prediction_preserved(browser, demo_server):
    page: Page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(demo_server.url + "/#/demo")

    input_text = "Nhân viên hỗ trợ thân thiện, nhưng cổng đăng ký học phần rất chậm và báo lỗi liên tục."
    page.locator("#sentence").fill(input_text)
    page.locator("#analyze").click()

    # Results panel appears
    expect(page.locator("#result-content")).to_be_visible(timeout=10000)

    # Both Sentiment and Topic headlines are displayed
    expect(page.locator("#sentiment")).to_be_visible()
    expect(page.locator("#sentiment-score")).to_be_visible()
    expect(page.locator("#topic")).to_be_visible()
    expect(page.locator("#topic-score")).to_be_visible()

    # Score stack and all sentiment labels are present
    expect(page.locator(".score-stack")).to_be_visible()
    expect(page.locator("#scores .score-row")).to_have_count(4)

    # Topic details has 10 topics
    expect(page.locator("#topic-scores .score-row")).to_have_count(10)

    page.screenshot(path=str(SCREENSHOT_DIR / "r03_local_prediction.png"))
    page.close()


# ============================================================================
# R04, R05, R06, R07: Bảng 4 cột P0, tương tác chọn qua lại, thanh đo,
# tổng đóng góp, cách tính mở rộng và không gọi LLM
# ============================================================================
def test_r04_to_r07_desktop_attribution_table_and_interaction(browser, demo_server):
    page: Page = browser.new_page(viewport={"width": 1440, "height": 900})

    # Track network requests to ensure NO /explanation endpoint is called (R07)
    explanation_calls = []

    def handle_request(req):
        if "/explanation" in req.url:
            explanation_calls.append(req.url)

    page.on("request", handle_request)
    page.goto(demo_server.url + "/#/demo")

    input_text = "Nhân viên hỗ trợ thân thiện, nhưng cổng đăng ký học phần rất chậm và báo lỗi liên tục."
    page.locator("#sentence").fill(input_text)
    page.locator("#analyze").click()

    # Wait for results and attribution table
    expect(page.locator("#result-content")).to_be_visible(timeout=10000)
    # Layout/selection assertions wait through the real worker's cold NLP load;
    # they do not impose a 15-second attribution SLA.
    expect(page.locator("#attribution-content")).to_be_visible(timeout=60000)

    # Revised brief: feedback precedes a compact list; no merged table cells.
    expect(page.locator("#attribution-content table")).to_have_count(0)
    expect(page.locator(".contribution-columns")).to_be_visible()

    # R04: Feedback cell displays interactive quote words
    word_marks = page.locator(".quote-container .word-mark")
    expect(word_marks.first).to_be_visible()
    assert word_marks.count() >= 3

    # R05: Bi-directional selection
    # 1. Click first word in the quote -> highlights first row in table
    first_mark = word_marks.first
    term_text = first_mark.inner_text()
    first_mark.click()
    expect(first_mark).to_have_attribute("aria-pressed", "true")

    # Selection detail text updates
    expect(page.locator(".selection-detail")).to_contain_text(term_text)

    # Corresponding table row button is also marked pressed
    phrase_buttons = page.locator("#attribution-content .phrase-button")
    expect(phrase_buttons.first).to_have_attribute("aria-pressed", "true")

    # 2. Click second phrase button in table -> highlights second word in quote
    if phrase_buttons.count() > 1:
        second_phrase = phrase_buttons.nth(1)
        second_phrase.click()
        expect(second_phrase).to_have_attribute("aria-pressed", "true")
        expect(word_marks.nth(1)).to_have_attribute("aria-pressed", "true")

    # R04: Gauge meters are present on weights
    meters = page.locator(".weight-meter")
    expect(meters.first).to_be_visible()
    expect(page.locator(".weight-meter i").first).to_be_attached()

    # R04: Single merged total cell displays total sign and unit
    total_cell = page.locator(".contribution-total")
    expect(total_cell).to_be_visible()
    expect(page.locator(".total-sign")).to_be_visible()
    expect(total_cell).to_contain_text("điểm phần trăm")

    # R06: Expandable "Cách tính tổng" shows calculation details
    method_details = page.locator("details.method-details")
    expect(method_details).to_be_visible()
    method_details.locator("summary").click()
    expect(method_details).to_have_attribute("open", "")
    expect(method_details).to_contain_text("Tổng đóng góp là tổng các trọng số trong toàn bộ danh sách")

    # R07: Verify NO LLM explanation block is present and NO LLM request was made
    expect(page.locator("#ai-content")).to_have_count(0)
    expect(page.locator("#ai-heading")).to_have_count(0)
    expect(page.locator("#ai-reading")).to_have_count(0)
    expect(page.locator("#ai-caution")).to_have_count(0)
    assert len(explanation_calls) == 0, f"Expected 0 explanation calls, got: {explanation_calls}"

    # Screenshot Desktop table view
    screenshot_table = SCREENSHOT_DIR / "r04_desktop_attribution_table.png"
    page.screenshot(path=str(screenshot_table), full_page=True)
    assert screenshot_table.exists()

    page.close()


# ============================================================================
# R08: P1 Donut cảm xúc, xếp hạng chủ đề chú ý và lọc dẫn chứng
# ============================================================================
def test_r08_sentiment_donut_and_topic_attention_ranking(browser, demo_server):
    page: Page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(demo_server.url + "/#/demo")
    expect(page.locator("#dataset-select")).to_have_count(0)
    expect(page.locator(".quick-add-box")).to_have_count(0)

    earlier = analyze_latest(page, demo_server.url, "Wifi ở phòng học hoạt động ổn định.")
    expect(page.locator(".overview-surface")).to_be_visible(timeout=10000)
    latest_text = negative_double_sentence("Thư viện hôm nay đóng cửa và phòng đọc nóng.")
    latest = analyze_latest(page, demo_server.url, latest_text)
    assert latest["dataset_id"] != earlier["dataset_id"]
    expect(page.locator(".overview-surface")).to_be_visible(timeout=10000)
    expect(page.locator("#contribution-donut")).to_be_visible(timeout=20000)
    attr_id = page.locator('.contribution-layout').get_attribute('data-attribution-id')
    attribution = httpx.get(demo_server.url + '/api/v1/attributions/' + attr_id).json()
    assert_shares(page, [g['contribution'] for g in attribution['groups']])
    expect(page.locator("#net-sentiment")).to_have_count(0)
    expect(page.locator('.distribution-pane')).not_to_contain_text('1 phản hồi')
    # Informational legend never filters whole-response evidence.
    page.locator('#contribution-legend li').first.click()
    expect(page.locator("#active-filters")).to_have_count(0)
    expect(page.locator("#evidence-list .evidence-row")).to_have_count(1)
    expect(page.locator("#evidence-list .evidence-text p")).to_have_text(latest_text)
    expect(page.locator("#distribution-heading")).to_have_text("Tỷ trọng đóng góp của cụm từ")

    clickable_attention = page.locator("#topic-attention .attention-row:not(:disabled)")
    expect(clickable_attention).to_have_count(1)
    expect(clickable_attention.locator(".attention-row-head b")).to_have_text("1")
    selected_topic = clickable_attention.locator(".attention-row-head strong").inner_text()
    clickable_attention.click()
    active_chips = page.locator("#active-filters .filter-chip")
    expect(active_chips).to_have_count(2)
    expect(active_chips.filter(has_text="Cảm xúc: Tiêu cực")).to_have_count(1)
    expect(active_chips.filter(has_text=f"Chủ đề: {selected_topic}")).to_have_count(1)
    expect(page.locator("#evidence-list .evidence-row")).to_have_count(1)
    expect(page.locator("#evidence-list .evidence-text p")).to_have_text(latest_text)
    expect(page.locator("#evidence-list .sentiment-badge")).to_have_text("Tiêu cực")
    expect(page.locator("#evidence-list .evidence-meta > span:last-child")).to_have_text(selected_topic)
    page.locator("#clear-filters").click()
    expect(page.locator("#active-filters")).to_have_count(0)
    expect(page.locator("#evidence-list .evidence-text p")).to_have_text(latest_text)
    page.screenshot(path=str(SCREENSHOT_DIR / "r08_overview_latest_sentence.png"), full_page=True)
    page.close()


# ============================================================================
# R09: Mạng chỉ dùng câu mới nhất; node/cạnh/nhóm và evidence cùng snapshot
# ============================================================================
def test_r09_word_network_graph_and_community_filter(browser, demo_server):
    page: Page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(demo_server.url + "/#/demo")
    earlier = analyze_latest(page, demo_server.url, "Wifi phòng học rất chậm, máy tính thường xuyên treo.")
    page.locator("#network").scroll_into_view_if_needed()
    # The single worker completes attribution before network. A cold software
    # fixture can spend >15s loading NLP resources; this checks source membership
    # and keyboard filtering, not a 15-second queue/cold-start SLA.
    expect(page.locator("#term-network .graph-node").first).to_be_visible(timeout=60000)

    latest_text = "Thư viện rộng rãi, phòng đọc yên tĩnh và bàn ghế sạch sẽ."
    latest = analyze_latest(page, demo_server.url, latest_text)
    assert latest["dataset_id"] != earlier["dataset_id"]
    page.locator("#network").scroll_into_view_if_needed()
    expect(page.locator('#term-network .graph-node[data-node="wifi"]')).to_have_count(0)
    expect(page.locator("#term-network .graph-node").first).to_be_visible(timeout=60000)
    network_response = httpx.get(f"{demo_server.url}/api/v1/datasets/{latest['dataset_id']}/network", params={
        "label_source": "ai", "run_id": latest["prediction"]["run_id"],
    })
    assert network_response.status_code == 200, network_response.text
    network = network_response.json()
    assert network["status"] == "completed"
    assert network["dataset_id"] == latest["dataset_id"] and network["label_source"] == "ai"
    assert network["source_item_count"] == network["scope_item_count"] == 1
    assert network["nodes"] and network["edges"] and network["communities"]
    assert all(node["count"] == 1 and node["item_ids"] == [latest["id"]] for node in network["nodes"])
    assert all(edge["weight"] == 1 and edge["item_ids"] == [latest["id"]] for edge in network["edges"])
    assert all(group["count"] == 1 and group["item_ids"] == [latest["id"]] for group in network["communities"])
    expect(page.locator("#term-network .graph-node")).to_have_count(len(network["nodes"]))
    expect(page.locator("#term-network .graph-edge")).to_have_count(len(network["edges"]))

    # Keyboard node selection and server-resolved evidence both refer to this quick item.
    first_node = page.locator("#term-network .graph-node").first
    first_node.focus()
    page.keyboard.press("Enter")
    expect(first_node).to_have_attribute("aria-pressed", "true")
    page.locator("#show-node-evidence").click()
    expect(page.locator("#evidence-list .evidence-row")).to_have_count(1)
    expect(page.locator("#evidence-list .evidence-text p")).to_have_text(latest_text)

    first_community = page.locator(".community-list .community-button").first
    first_community.click()
    expect(first_community).to_have_attribute("aria-pressed", "true")
    expect(first_community).to_contain_text("1 phản hồi liên quan")
    page.locator("#show-node-evidence").click()
    expect(page.locator("#active-filters .filter-chip")).to_have_count(1)
    expect(page.locator("#evidence-list .evidence-row")).to_have_count(1)
    expect(page.locator("#evidence-list .evidence-text p")).to_have_text(latest_text)
    page.screenshot(path=str(SCREENSHOT_DIR / "r09_latest_sentence_network.png"), full_page=True)
    page.close()
