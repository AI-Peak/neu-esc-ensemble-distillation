"""R1/R2/R7 regressions against production assets and isolated test servers.

The registry in the harness is a software double, never live ED evidence.
"""
import time

import httpx
import pytest
from playwright.sync_api import expect


def create_item(client, name="Regression review"):
    response = client.post("/datasets", json={"name": name, "profile": "uit",
                                              "items": [{"text": "Giảng viên giải thích rõ ràng."}]})
    assert response.status_code == 201, response.text
    dataset = response.json()
    item = client.get(f"/datasets/{dataset['id']}/items").json()["items"][0]
    return dataset, item


def analyze(client, dataset):
    response = client.post("/analysis-runs", json={"dataset_id": dataset["id"]})
    assert response.status_code == 202, response.text
    run = response.json()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{run['job_id']}").json()
        if job["status"] in ("completed", "completed_with_errors", "failed"):
            assert job["status"] == "completed", job
            return run
        time.sleep(0.05)
    raise AssertionError("Test-only analysis did not finish")


def open_item(page, server, dataset, item):
    page.goto(server.url + f"/#/datasets/{dataset['id']}")
    page.get_by_role("button", name=item["text"], exact=True).click()
    expect(page.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_be_visible()


def reconnect_and_refetch(page, item):
    # Production disables refetch-on-focus but refreshes stale queries on network
    # reconnect. Let its documented three-second stale window elapse first.
    page.wait_for_timeout(3100)
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    with page.expect_response(lambda r: f"/api/v1/items/{item['id']}" in r.url and r.request.method == "GET"):
        page.evaluate("window.dispatchEvent(new Event('online'))")


def test_r1_note_only_across_disagreeing_runs_preserves_confirmation(browser, varying_server, screenshot_dir):
    with httpx.Client(base_url=varying_server.url + "/api/v1") as client:
        dataset, item = create_item(client)
        first_run = analyze(client, dataset)
        first = client.get(f"/items/{item['id']}").json()["prediction"]
        saved = client.put(f"/items/{item['id']}/review", json={
            "task": "sentiment", "status": "confirmed", "label_id": 1, "note": "Run A",
            "run_id": first_run["id"], "expected_revision": 1, "expected_review_revision": 0,
        })
        assert saved.status_code == 200, saved.text
        second_run = analyze(client, dataset)
        second = client.get(f"/items/{item['id']}").json()["prediction"]
        assert first["sentiment"]["label_id"] == 1 and second["sentiment"]["label_id"] == 2
        with browser.new_context(viewport={"width": 1440, "height": 1000}) as context:
            page = context.new_page()
            open_item(page, varying_server, dataset, item)
            expect(page.get_by_test_id("confirmed-label-sentiment")).to_have_text("Trung tính")
            expect(page.get_by_test_id("confirmed-source-sentiment")).to_contain_text(first["id"])
            page.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill("Chỉ sửa note khi đang xem B")
            page.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
            expect(page.get_by_text("Đã lưu · bản duyệt 2", exact=True)).to_be_visible()
            review = client.get(f"/items/{item['id']}").json()["reviews"]["sentiment"]
            assert review["label_id"] == 1 and review["source_prediction_id"] == first["id"]
            assert review["note"] == "Chỉ sửa note khi đang xem B"
            page.screenshot(path=str(screenshot_dir / "r1-preserved-confirmation.png"), full_page=True)
            # Reopening each historical view must retain the human label/source.
            page.get_by_role("button", name="Đóng chi tiết", exact=True).click()
            page.get_by_label("Lần phân tích", exact=True).select_option(first_run["id"])
            page.get_by_role("button", name=item["text"], exact=True).click()
            expect(page.get_by_test_id("confirmed-label-sentiment")).to_have_text("Trung tính")
            page.get_by_role("button", name="Đóng chi tiết", exact=True).click()
            page.get_by_label("Lần phân tích", exact=True).select_option(second_run["id"])
            page.get_by_role("button", name=item["text"], exact=True).click()
            page.get_by_role("button", name="Xác nhận dự đoán đang xem: cảm xúc", exact=True).click()
            expect(page.get_by_test_id("confirmed-label-sentiment")).to_have_text("Tích cực")
            page.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
            expect(page.get_by_text("Đã lưu · bản duyệt 3", exact=True)).to_be_visible()
            updated = client.get(f"/items/{item['id']}").json()
            assert updated["reviews"]["sentiment"]["label_id"] == 2
            assert updated["reviews"]["sentiment"]["source_prediction_id"] == second["id"]
            assert updated["prediction"] == second
            assert client.get(f"/items/{item['id']}", params={"run_id": first_run["id"]}).json()["prediction"] == first
            history = client.get(f"/items/{item['id']}/reviews").json()
            assert [(r["label_id"], r["source_prediction_id"]) for r in history] == [
                (1, first["id"]), (1, first["id"]), (2, second["id"])]


@pytest.mark.parametrize("background_refetch", [False, True], ids=["409", "background-refetch"])
@pytest.mark.parametrize("task, task_name", [("sentiment", "cảm xúc"), ("topic", "chủ đề")])
def test_r2_two_context_drafts_require_deliberate_resolution(browser, app_server, screenshot_dir, background_refetch, task, task_name):
    with httpx.Client(base_url=app_server.url + "/api/v1") as client:
        dataset, item = create_item(client)
        with browser.new_context() as first_context, browser.new_context() as second_context:
            first_page, second_page = first_context.new_page(), second_context.new_page()
            open_item(first_page, app_server, dataset, item)
            open_item(second_page, app_server, dataset, item)
            for page, label, note in [(first_page, "0", "Bản nháp cần giữ"),
                                      (second_page, "2", "Bản server từ trình duyệt hai")]:
                page.get_by_label(f"Trạng thái {task_name}", exact=True).select_option("corrected")
                page.get_by_label(f"Nhãn {task_name} đã sửa", exact=True).select_option(label)
                page.get_by_role("textbox", name=f"Ghi chú {task_name}", exact=True).fill(note)
            second_page.get_by_role("button", name=f"Lưu {task_name}", exact=True).click()
            expect(second_page.get_by_text("Đã lưu · bản duyệt 1", exact=True)).to_be_visible()
            save = first_page.get_by_role("button", name=f"Lưu {task_name}", exact=True)
            if background_refetch:
                reconnect_and_refetch(first_page, item)
            else:
                with first_page.expect_response(lambda r: r.request.method == "PUT" and "/review" in r.url) as response:
                    save.click()
                assert response.value.status == 409
            conflict = first_page.get_by_test_id(f"review-conflict-{task}")
            expect(conflict).to_be_visible()
            expect(conflict).to_contain_text("Bản server từ trình duyệt hai")
            expect(first_page.get_by_role("textbox", name=f"Ghi chú {task_name}", exact=True)).to_have_value("Bản nháp cần giữ")
            expect(save).to_be_disabled()
            # A repeated activation cannot silently upgrade the old draft's base.
            save.evaluate("button => button.click()")
            server_item = client.get(f"/items/{item['id']}").json()
            server_review = server_item["reviews"][task]
            assert server_review["revision"] == 1 and server_review["label_id"] == 2
            assert server_item["reviews"]["topic" if task == "sentiment" else "sentiment"] is None
            first_page.screenshot(path=str(screenshot_dir / f"r2-conflict-{task}-{background_refetch}.png"), full_page=True)
            first_page.get_by_role("button", name=f"Áp lại bản nháp: {task_name}", exact=True).click()
            expect(save).to_be_enabled()
            save.click()
            expect(first_page.get_by_text("Đã lưu · bản duyệt 2", exact=True)).to_be_visible()
            applied = client.get(f"/items/{item['id']}").json()["reviews"][task]
            assert applied["label_id"] == 0 and applied["note"] == "Bản nháp cần giữ"
            # The second context can deliberately load the new server version.
            second_page.get_by_role("textbox", name=f"Ghi chú {task_name}", exact=True).fill("Bản nháp thứ hai")
            reconnect_and_refetch(second_page, item)
            expect(second_page.get_by_test_id(f"review-conflict-{task}")).to_be_visible()
            second_page.get_by_role("button", name=f"Tải bản server: {task_name}", exact=True).click()
            expect(second_page.get_by_role("textbox", name=f"Ghi chú {task_name}", exact=True)).to_have_value("Bản nháp cần giữ")
            expect(second_page.get_by_label(f"Nhãn {task_name} đã sửa", exact=True)).to_have_value("0")
            expect(second_page.get_by_role("button", name=f"Lưu {task_name}", exact=True)).to_be_disabled()


@pytest.mark.parametrize("delimiter", ["\t", ",", ";", "|"], ids=["tab", "comma", "semicolon", "pipe"])
def test_r7_manual_delimiter_preview_import_and_auto_detect(browser, app_server, delimiter):
    with browser.new_context() as context, httpx.Client(base_url=app_server.url + "/api/v1") as client:
        page = context.new_page()
        page.goto(app_server.url)
        page.get_by_test_id("create-dataset").click()
        page.get_by_test_id("dataset-name").fill("Nhập dấu phân cách")
        content = f"text{delimiter}meta\r\nPhòng học có thiết bị tốt.{delimiter}Đào tạo\r\n"
        with page.expect_response(lambda r: "/imports/preview" in r.url) as auto:
            page.get_by_test_id("file-upload").set_input_files({
                "name": "phan-hoi.csv", "mimeType": "text/csv", "buffer": content.encode("utf-8-sig")})
        assert auto.value.status == 200
        assert auto.value.json()["delimiter"] == delimiter
        expect(page.get_by_test_id("text-column")).to_have_value("text")
        option = page.get_by_label("Dấu phân cách")
        # Selecting by label catches the original JSX two-character tab value.
        labels = {"\t": "Tab", ",": "Dấu phẩy (,)", ";": "Dấu chấm phẩy (;)", "|": "Dấu gạch đứng (|)"}
        with page.expect_response(lambda r: "/imports/preview" in r.url) as manual:
            option.select_option(label=labels[delimiter])
        assert manual.value.status == 200, manual.value.text()
        assert manual.value.json()["delimiter"] == delimiter
        assert manual.value.json()["columns"] == ["text", "meta"]
        expect(page.locator(".preview-table")).to_contain_text("Đào tạo")
        page.get_by_test_id("import-confirm").click()
        expect(page.get_by_role("heading", name="Nhập dấu phân cách", exact=True)).to_be_visible()
        dataset_id = page.url.split("/datasets/")[-1]
        imported = client.get(f"/datasets/{dataset_id}/items").json()["items"]
        assert len(imported) == 1 and imported[0]["text"] == "Phòng học có thiết bị tốt."
        assert imported[0]["metadata"]["meta"] == "Đào tạo"
