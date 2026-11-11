import csv
import io
import re

import httpx
from playwright.sync_api import expect


def test_missing_model_is_honest_and_mobile_import_persists(browser, missing_server, screenshot_dir):
    context = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(missing_server.url + "/#/")
    page.get_by_test_id("create-dataset").click()
    page.get_by_test_id("dataset-name").fill("Kiểm tra tiếng Việt trên điện thoại")
    page.get_by_role("tab", name="Dán văn bản", exact=True).click()
    page.get_by_test_id("paste-input").fill("Phòng học cần thêm quạt.\nGiảng viên giải thích dễ hiểu.")
    page.get_by_test_id("import-confirm").click()
    expect(page.get_by_role("heading", name="Kiểm tra tiếng Việt trên điện thoại", exact=True)).to_be_visible()
    expect(page.get_by_test_id("analyze")).to_be_disabled()
    expect(page.get_by_text("Chưa thể phân tích AI", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    page.screenshot(path=str(screenshot_dir / "mobile-missing-model.png"), full_page=True)
    dataset_id = page.url.split("/datasets/")[-1]
    response = httpx.post(missing_server.url + "/api/v1/analysis-runs", json={"dataset_id": dataset_id})
    assert response.status_code == 409 and response.json()["code"] == "MODEL_UNAVAILABLE"
    missing_server.restart()
    page.reload()
    expect(page.get_by_role("heading", name="Kiểm tra tiếng Việt trên điện thoại", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Phòng học cần thêm quạt.", exact=True)).to_be_visible()
    assert not failures
    context.close()


def test_csv_analyze_filter_review_export_restart(browser, app_server, screenshot_dir, tmp_path):
    """This full UI flow uses an explicitly test-only registry, never claims live ED."""
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(app_server.url + "/#/")
    page.get_by_test_id("create-dataset").click()
    page.get_by_test_id("dataset-name").fill("E2E · Phản hồi tháng 11")
    content = 'text;ghi_chu\r\n"Phòng học nóng,\nmáy chiếu bị mờ.";"=1+1"\r\n"Giảng viên giải thích rõ ràng.";"Góp ý thật"\r\n"Cần thêm câu lạc bộ.";"Giữ metadata"\r\n'
    page.get_by_test_id("file-upload").set_input_files({"name": "phan-hoi.csv", "mimeType": "text/csv", "buffer": content.encode("utf-8-sig")})
    expect(page.get_by_test_id("text-column")).to_have_value("text")
    page.get_by_test_id("import-confirm").click()
    expect(page.get_by_role("heading", name="E2E · Phản hồi tháng 11", exact=True)).to_be_visible()
    dataset_id = page.url.split("/datasets/")[-1]
    page.get_by_test_id("analyze").click()
    expect(page.get_by_text("3/3 kết quả đã lưu", exact=True)).to_be_visible(timeout=20000)
    client = httpx.Client(base_url=app_server.url + "/api/v1")
    original = client.get(f"/datasets/{dataset_id}/items").json()["items"]
    first = original[0]
    assert all(item["prediction"]["model_id"] == "TEST-DOUBLE-NOT-A-MODEL" for item in original)
    # Click the real summary chart to apply a filter to the table.
    sentiment_id = first["prediction"]["sentiment"]["label_id"]
    profile = client.get("/profiles").json()[0]
    name = next(label["name"] for label in profile["sentiment"] if label["id"] == sentiment_id)
    page.locator(".distribution").first.get_by_role("button", name=re.compile(re.escape(name) + r":")).click()
    expect(page.get_by_label("Lọc cảm xúc")).to_have_value(str(sentiment_id))
    page.get_by_label("Lọc cảm xúc").select_option("")
    page.get_by_role("button", name=first["text"], exact=True).click()
    expect(page.get_by_role("heading", name=f"Dòng {first['source_row']}", exact=True)).to_be_visible()
    # Per-task review controls are exercised below using stable labels from the UI.
    page.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    page.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option(str((sentiment_id + 1) % len(profile["sentiment"])))
    page.get_by_label("Ghi chú cảm xúc").fill("=Ghi chú do người rà soát")
    page.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    expect(page.get_by_text("Đã lưu · bản duyệt 1", exact=True)).to_be_visible()
    updated = client.get(f"/items/{first['id']}").json()
    assert updated["prediction"] == first["prediction"]
    assert updated["reviews"]["topic"] is None
    assert updated["reviews"]["sentiment"]["status"] == "corrected"
    page.screenshot(path=str(screenshot_dir / "desktop-review.png"), full_page=True)
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    page.get_by_test_id("export").click()
    page.get_by_role("button", name="Tạo bản chụp CSV", exact=True).click()
    with page.expect_download() as pending:
        page.get_by_role("link", name="Tải CSV", exact=True).click()
    download = pending.value
    destination = tmp_path / "snapshot.csv"
    download.save_as(destination)
    raw = destination.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    exported = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert len(exported) == 3
    selected = next(item for item in exported if item["item_id"] == first["id"])
    assert selected["ai_sentiment"] == str(sentiment_id)
    assert selected["review_sentiment_note"].startswith("'=Ghi chú")
    snapshot = raw
    page.get_by_role("button", name="Đóng", exact=True).last.click()
    app_server.restart()
    page.reload()
    expect(page.get_by_role("heading", name="E2E · Phản hồi tháng 11", exact=True)).to_be_visible()
    after = client.get(f"/items/{first['id']}").json()
    assert after["reviews"]["sentiment"] == updated["reviews"]["sentiment"]
    assert after["prediction"] == first["prediction"]
    assert destination.read_bytes() == snapshot
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert not failures
    client.close()
    context.close()


def test_mobile_review_text_revisions_and_quick_analysis_profiles(browser, app_server, screenshot_dir):
    client = httpx.Client(base_url=app_server.url + "/api/v1")
    neu = client.post("/datasets", json={"name": "NEU mobile", "profile": "neu", "items": [{"text": "Em cần hỗ trợ đăng ký học."}]}).json()
    uit = client.post("/datasets", json={"name": "UIT mobile", "profile": "uit", "items": [{"text": "Thầy giảng rõ ràng."}]}).json()
    item = client.get(f"/datasets/{neu['id']}/items").json()["items"][0]
    context = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    page = context.new_page()
    failures = []
    page.on("pageerror", lambda error: failures.append(str(error)))
    page.goto(app_server.url + f"/#/datasets/{neu['id']}")
    page.get_by_role("button", name=item["text"], exact=True).click()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    page.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("1")
    page.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    expect(page.get_by_text("Đã lưu · bản duyệt 1", exact=True)).to_be_visible()
    page.get_by_role("button", name="Hoàn tác lần lưu", exact=True).click()
    expect(page.get_by_text("Đã lưu · bản duyệt 2", exact=True)).to_be_visible()
    assert client.get(f"/items/{item['id']}").json()["reviews"]["sentiment"]["status"] == "unreviewed"
    page.get_by_role("button", name="Sửa văn bản", exact=True).click()
    page.get_by_label("Sửa văn bản phản hồi", exact=True).fill("Nội dung sau khi sửa dấu tiếng Việt.")
    page.get_by_role("button", name="Lưu phiên bản văn bản", exact=True).click()
    expect(page.get_by_text("Phiên bản 2", exact=True)).to_be_visible()
    revised = client.get(f"/items/{item['id']}").json()
    assert revised["prediction"] is None and revised["reviews"]["sentiment"] is None
    page.screenshot(path=str(screenshot_dir / "mobile-review.png"), full_page=True)
    assert page.get_by_role("dialog").evaluate("element => element.scrollWidth <= element.clientWidth + 1")
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    page.get_by_role("button", name="Thử một câu", exact=True).first.click()
    expect(page).to_have_url(re.compile(r"#/demo$"))
    page.locator("#schema-select").select_option("uit")
    page.locator("#sentence").fill("Phòng học có thiết bị tốt.")
    page.locator("#analyze").click()
    expect(page.locator("#result-content")).to_be_visible(timeout=20000)
    expect(page.locator("#scores .score-row")).to_have_count(3)
    expect(page.locator("#topic-scores .score-row")).to_have_count(4)
    destination = page.get_by_role("combobox", name="Lưu câu vào bộ phản hồi cùng hệ nhãn", exact=True)
    expect(destination).to_contain_text("UIT mobile")
    expect(destination).not_to_contain_text("NEU mobile")
    destination.select_option(uit["id"])
    page.get_by_role("button", name="Thêm câu vào bộ", exact=True).click()
    expect(page.get_by_role("button", name="Đã thêm câu", exact=True)).to_be_visible()
    assert len(client.get("/datasets").json()) == 2  # Quick temp dataset never in durable list.
    assert client.get(f"/datasets/{uit['id']}").json()["item_count"] == 2
    assert not failures
    client.close()
    context.close()


def test_laptop_keyboard_focus_and_text_contrast(browser, missing_server, screenshot_dir):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.goto(missing_server.url + "/#/")
    expect(page.get_by_test_id("create-dataset")).to_be_visible()
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="Đến nội dung chính", exact=True)).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("main")).to_be_focused()
    assert "#main" not in page.url  # Skip link must not change the application's hash route.
    page.get_by_role("button", name="Thử một câu", exact=True).first.click()
    expect(page).to_have_url(re.compile(r"#/demo$"))
    expect(page.locator("#sentence")).to_be_visible()
    page.go_back()
    expect(page.get_by_test_id("create-dataset")).to_be_visible()
    page.get_by_role("button", name="Thử một câu", exact=True).first.focus()
    expect(page.get_by_role("button", name="Thử một câu", exact=True).first).to_be_focused()
    ratios = page.evaluate("""() => {
        const root = getComputedStyle(document.documentElement);
        const canvas = document.createElement('canvas'); canvas.width=1; canvas.height=1;
        const ctx=canvas.getContext('2d', {willReadFrequently:true});
        function luminance(color) {
            ctx.clearRect(0,0,1,1);ctx.fillStyle=color;ctx.fillRect(0,0,1,1);
            const pixel=ctx.getImageData(0,0,1,1).data;
            const rgb=Array.from(pixel).slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});
            return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
        }
        function ratio(a,b) {const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)}
        const primary=getComputedStyle(document.querySelector('[data-testid="create-dataset"]'));
        return {
            ink:ratio(root.getPropertyValue('--ink'),'white'),
            muted:ratio(root.getPropertyValue('--muted'),root.getPropertyValue('--surface')),
            primary:ratio(primary.color,primary.backgroundColor)
        };
    }""")
    assert ratios["ink"] >= 7
    assert ratios["muted"] >= 4.5
    assert ratios["primary"] >= 4.5
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    page.screenshot(path=str(screenshot_dir / "laptop-empty.png"), full_page=True)
    context.close()
