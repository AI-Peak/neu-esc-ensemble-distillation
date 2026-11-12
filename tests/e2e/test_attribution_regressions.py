"""Browser regressions with explicitly marked, internally consistent API doubles.

These tests prove UI ownership/validation/layout; they are not model evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse
import uuid

import pytest
from playwright.sync_api import expect

PROFILES = json.loads((Path(__file__).resolve().parents[2] / "services/profiles.json").read_text(encoding="utf-8"))


def utf16(value):
    return len(value.encode("utf-16-le")) // 2


class AttributionDouble:
    def __init__(self, page, *, profile="neu", winner=1, group_count=1):
        self.page, self.profile, self.winner, self.group_count = page, profile, winner, group_count
        self.jobs, self.results = {}, {}
        self.posts, self.gets, self.cancels, self.keys = [], [], [], []
        self.held = []
        self.held_gets = []
        self.hold_next = False
        self.hold_next_get = False
        self.post_error = None
        self.get_status = None
        self.get_http = None
        self.transport_failures = 0
        self.get_transport_failures = 0
        self.cancel_completed = False
        self.mutate = None
        self.profiles = copy.deepcopy(PROFILES)
        for profile_row in self.profiles:
            profile_row["model"] = dict(available=True, reason=None, model_id="TEST-DOUBLE-NOT-A-MODEL",
                model_version="attribution-ui-double-v2", schema_id=profile_row["schema_id"])
        page.route("**/api/v1/**", self.route)

    def route(self, route):
        request = route.request
        path = urlparse(request.url).path.removeprefix("/api/v1")
        if path == "/profiles": return route.fulfill(json=self.profiles)
        if path == "/datasets": return route.fulfill(json=[])
        if path == "/quick-analysis" and request.method == "POST":
            body = request.post_data_json
            index = len(self.jobs) + 1
            prof = next(p for p in self.profiles if p["id"] == body["profile"])
            winner = self.winner if body["profile"] == self.profile else 1
            sentiment = [.1 / (len(prof["sentiment"]) - 1)] * len(prof["sentiment"])
            sentiment[winner] = .9
            topic = [.1 / (len(prof["topic"]) - 1)] * len(prof["topic"])
            topic[0] = .9
            identity = dict(profile=prof["id"], schema_id=prof["schema_id"], model_id=prof["model"]["model_id"],
                model_version=prof["model"]["model_version"], manifest_sha256="a"*64, preprocessing_sha256="b"*64,
                mode="cpu-fp32-eval")
            pred = dict(id=f"p{index}", item_id=f"i{index}", revision_id=f"r{index}", run_id=f"run{index}",
                model_id=identity["model_id"], model_version=identity["model_version"], schema_id=prof["schema_id"],
                sentiment=dict(label_id=winner, scores=sentiment), topic=dict(label_id=0, scores=topic),
                execution_identity=identity, token_count_before_truncation=self.group_count+2, truncated=False, warnings=[], duration_ms=1)
            item = dict(id=f"i{index}", dataset_id=f"d{index}", revision_id=f"r{index}", revision=1,
                source_row=1, text=body["text"], metadata={}, reference={}, prediction=pred,
                reviews=dict(sentiment=None, topic=None), effective=dict(sentiment=winner, topic=0),
                stale=False, error=None)
            job_id = f"job{index}"
            self.jobs[job_id] = dict(id=job_id, run_id=f"run{index}", kind="quick", status="completed", result=item)
            return route.fulfill(status=202, json=dict(job_id=job_id, run_id=f"run{index}"))
        if path.startswith("/jobs/"):
            job_id = path.split("/")[2]
            return route.fulfill(json=self.jobs[job_id])
        if path.startswith("/quick-analysis/") and path.endswith("/attribution"):
            job_id = path.split("/")[2]
            self.posts.append(job_id)
            self.keys.append(request.headers.get("idempotency-key"))
            if self.transport_failures:
                self.transport_failures -= 1
                return route.abort("failed")
            attr_id = f"attr{len(self.posts)}"
            result = self.completed(attr_id, job_id, request.post_data_json["target"])
            if self.mutate: self.mutate(result)
            self.results[attr_id] = result
            if self.hold_next:
                self.hold_next = False
                self.held.append((route, result))
                return
            if self.post_error:
                return route.fulfill(status=self.post_error, json=dict(code="TEST_ERROR", message="Lỗi cũ A"))
            return route.fulfill(status=202 if self.get_status or self.get_http else 200,
                json=dict(attribution_id=attr_id, status="queued", groups=[], progress={}) if self.get_status or self.get_http else result)
        if path.startswith("/attributions/"):
            attr_id = path.split("/")[2]
            if path.endswith("/cancel"):
                self.cancels.append(attr_id)
                if self.cancel_completed:
                    self.get_status = None
                    return route.fulfill(json=dict(attribution_id=attr_id, status="completed"))
                return route.fulfill(json=dict(attribution_id=attr_id, status="cancelled"))
            self.gets.append(attr_id)
            if self.hold_next_get:
                self.hold_next_get = False
                self.held_gets.append((route, copy.deepcopy(self.results[attr_id])))
                return
            if self.get_transport_failures:
                self.get_transport_failures -= 1
                return route.abort("failed")
            if self.get_http:
                return route.fulfill(status=self.get_http, json=dict(code="SOURCE_GONE", message="Nguồn hết hạn"))
            result = copy.deepcopy(self.results[attr_id])
            if self.get_status:
                result.update(status=self.get_status, error=dict(code="TEST_UNSUPPORTED", message="Mapping/truncation chưa hỗ trợ"))
            return route.fulfill(json=result)
        route.fulfill(status=404, json=dict(code="NOT_FOUND", message="Double route not defined"))

    def completed(self, attr_id, job_id, target):
        item = self.jobs[job_id]["result"]
        pred = item["prediction"]
        prof = next(p for p in self.profiles if p["id"] == pred["execution_identity"]["profile"])
        scores = pred["sentiment"]["scores"]
        if target["kind"] == "label_score": output = scores[target["label_id"]]*100
        else:
            positive = next(i for i,l in enumerate(prof["sentiment"]) if l["key"].lower()=="positive")
            negative = next(i for i,l in enumerate(prof["sentiment"]) if l["key"].lower()=="negative")
            output = 100*(scores[positive]-scores[negative])
        spans = [(0, len(item["text"]))] if self.group_count == 1 else [m.span() for m in re.finditer(r"\S+", item["text"])]
        groups = [dict(id=f"g{i}", text=item["text"][start:end], start_utf16=utf16(item["text"][:start]),
            end_utf16=utf16(item["text"][:end]), token_indices=[i+1], contribution=output/len(spans))
            for i,(start,end) in enumerate(spans)]
        return dict(attribution_id=attr_id, status="completed", source=dict(source_job_id=job_id, source_prediction_id=pred["id"],
            item_id=item["id"], revision_id=item["revision_id"], run_id=pred["run_id"],
            text_hash=hashlib.sha256(item["text"].encode()).hexdigest(), profile_id=prof["id"], schema_id=prof["schema_id"],
            model_id=pred["model_id"], model_version=pred["model_version"], execution_identity=pred["execution_identity"]),
            method=dict(id="permutation_shapley", version="2.0", grouping_version="v2", baseline_policy="all_groups_masked",
                target=target, unit="percentage_points", seed=42, requested_permutations=8, completed_permutations=8, evaluated_coalitions=2+len(spans)*4),
            coverage=dict(truncated=False, input_token_count=len(spans)+2, mapping_status="exact", analyzed_spans=len(spans),
                fixed_token_policy="special_tokens_only", explained_token_indices=list(range(1,len(spans)+1))),
            groups=groups, aggregate=dict(baseline_value=0, total_contribution=output, target_output=output, additivity_residual=0),
            progress=dict(completed_batches=2, total_batches=2), error=None)

    def analyze(self, text="Câu mới kiểm thử UI."):
        self.page.locator("#sentence").fill(text)
        self.page.locator("#analyze").click()
        expect(self.page.locator("#result-content")).to_be_visible()


def test_section_navigation_keeps_demo_route_and_input(browser, app_server):
    page = browser.new_page()
    AttributionDouble(page)
    page.goto(app_server.url + "/#/demo")
    page.locator("#sentence").fill("Giữ câu đang nhập.")
    for anchor in ["#network", "#overview", "#analysis"]:
        page.locator(f'.header-inner nav a[href="{anchor}"]').click()
        assert page.url.endswith("/#/demo")
        expect(page.locator("#sentence")).to_have_value("Giữ câu đang nhập.")
    page.close()


@pytest.mark.parametrize("profile,winner,kind", [("neu",0,"label_score"),("neu",1,"polarity_margin"),
    ("neu",2,"polarity_margin"),("neu",3,"label_score"),("uit",0,"polarity_margin"),
    ("uit",1,"label_score"),("uit",2,"polarity_margin")])
def test_all_profile_targets_match_request_number_and_legend(browser, app_server, profile, winner, kind):
    page = browser.new_page()
    double = AttributionDouble(page, profile=profile, winner=winner)
    page.goto(app_server.url + "/#/demo")
    if profile != "neu": page.locator("#schema-select").select_option(profile)
    double.analyze()
    expect(page.locator(".attribution-table")).to_be_visible()
    assert page.locator(".attribution-table thead th").nth(2).evaluate("cell => cell.scrollWidth <= cell.clientWidth + 1")
    result = next(iter(double.results.values()))
    assert result["method"]["target"]["kind"] == kind
    assert uuid.UUID(double.keys[0]).version == 4
    assert len(double.posts) == 1
    if kind == "label_score":
        assert result["method"]["target"]["label_id"] == winner
        expect(page.locator(".direction-legend")).to_contain_text("Tăng điểm")
        expect(page.locator(".total-sign")).to_contain_text("90,0")
        expect(page.locator(".word-mark")).to_have_class(re.compile("label-increase-mark"))
    else:
        expect(page.locator(".direction-legend")).to_contain_text("Nghiêng tích cực")
        assert "label_id" not in result["method"]["target"]
    page.close()


@pytest.mark.parametrize("late", ["completed", "failure", "queued"])
def test_late_post_a_does_not_replace_b_and_cancels_a_handle(browser, app_server, late):
    page = browser.new_page()
    double = AttributionDouble(page)
    double.hold_next = True
    page.goto(app_server.url + "/#/demo")
    double.analyze("Câu A đang chờ.")
    expect(page.locator("#word-analysis")).to_contain_text("Đang tính")
    page.wait_for_function("() => true")
    assert len(double.held) == 1
    double.analyze("Câu B hiện hành.")
    expect(page.locator(".quote-text")).to_have_text("Câu B hiện hành.")
    route, result = double.held.pop()
    if late == "failure": route.fulfill(status=500, json=dict(code="TEST_FAILURE", message="Lỗi cũ A"))
    else:
        if late == "queued": result["status"] = "queued"
        route.fulfill(json=result)
    page.wait_for_timeout(250)
    expect(page.locator(".quote-text")).to_have_text("Câu B hiện hành.")
    expect(page.locator("#word-analysis .notice.error")).to_have_count(0)
    expect(page.locator('.contribution-layout')).to_have_attribute('data-attribution-id', 'attr2')
    if late != "failure": assert result["attribution_id"] in double.cancels
    assert "attr2" not in double.cancels
    page.close()


@pytest.mark.parametrize("action", ["clear", "profile", "unmount", "cancel"])
def test_pending_post_abandoned_operations_cancel_late_handle(browser, app_server, action):
    page = browser.new_page()
    double = AttributionDouble(page)
    double.hold_next = True
    page.goto(app_server.url + "/#/demo")
    double.analyze()
    expect(page.locator("#word-analysis")).to_contain_text("Đang tính")
    if action == "clear": page.locator("#clear").click()
    elif action == "profile": page.locator("#schema-select").select_option("uit")
    elif action == "cancel": page.get_by_role("button", name="Hủy tính toán").click()
    else: page.goto(app_server.url + "/#/help")
    route, result = double.held.pop()
    route.fulfill(json=result)
    page.wait_for_timeout(250)
    assert result["attribution_id"] in double.cancels
    expect(page.locator(".attribution-table")).to_have_count(0)
    expect(page.locator('#contribution-donut')).to_have_count(0)
    page.close()


@pytest.mark.parametrize("terminal_state,http_status", [("unsupported",None),("failed",None),("cancelled",None),
    (None,404),(None,410),(None,409),(None,422)])
def test_terminal_and_http_errors_stop_polling_keep_prediction(browser, app_server, terminal_state, http_status):
    page = browser.new_page()
    double = AttributionDouble(page)
    double.get_status, double.get_http = terminal_state, http_status
    page.goto(app_server.url + "/#/demo")
    double.analyze()
    expect(page.locator("#word-analysis .notice.error")).to_be_visible()
    count = len(double.gets)
    expect(page.locator('#contribution-donut')).to_have_count(0)
    expect(page.locator('.distribution-pane [role="status"]')).to_be_visible()
    page.wait_for_timeout(1800)
    assert len(double.gets) == count == 1
    expect(page.locator("#sentiment")).to_be_visible()
    expect(page.get_by_role("button", name="Hủy tính toán")).to_have_count(0)
    if http_status is None:
        double.get_status = None
        page.get_by_role("button", name="Thử lại tính đóng góp").click()
        expect(page.locator(".attribution-table")).to_be_visible()
        assert len(set(double.keys)) == 2
        assert len(double.jobs) == 1
    else:
        expect(page.get_by_role("button", name="Thử lại tính đóng góp")).to_have_count(0)
    page.close()


def test_transport_retry_reuses_uuid_double_submit_creates_one_operation(browser, app_server):
    page = browser.new_page()
    double = AttributionDouble(page)
    double.transport_failures = 1
    page.goto(app_server.url + "/#/demo")
    page.locator("#sentence").fill("Câu retry mạng.")
    page.locator("#analysis-form").evaluate("form => { form.requestSubmit(); form.requestSubmit(); }")
    expect(page.locator(".attribution-table")).to_be_visible()
    assert len(double.jobs) == 1
    assert len(double.posts) == 2
    assert len(set(double.keys)) == 1
    page.close()


def test_get_transport_failure_recovers_existing_handle_without_new_prediction_or_post(browser, app_server):
    page = browser.new_page()
    double = AttributionDouble(page)
    double.get_status, double.get_transport_failures = "running", 3
    page.goto(app_server.url + "/#/demo")
    double.analyze()
    expect(page.locator("#word-analysis .notice.error")).to_be_visible()
    assert len(double.gets) == 3
    page.wait_for_timeout(1000)
    assert len(double.gets) == 3
    double.get_status = None
    page.get_by_role("button", name="Thử lại tính đóng góp").click()
    expect(page.locator(".attribution-table")).to_be_visible()
    assert len(double.gets) == 4 and len(double.posts) == len(double.jobs) == 1
    page.close()


@pytest.mark.parametrize("status", ["queued", "running"])
def test_cancel_active_attribution_stops_polling_and_retry_gets_new_handle(browser, app_server, status):
    page = browser.new_page()
    double = AttributionDouble(page)
    double.get_status = status
    page.goto(app_server.url + "/#/demo")
    double.analyze()
    expect(page.get_by_role("button", name="Hủy tính toán")).to_be_visible()
    page.wait_for_timeout(100)
    page.get_by_role("button", name="Hủy tính toán").click()
    count = len(double.gets)
    page.wait_for_timeout(1000)
    assert len(double.gets) == count and double.cancels == ["attr1"]
    expect(page.locator("#sentiment")).to_be_visible()
    double.get_status = None
    page.get_by_role("button", name="Thử lại tính đóng góp").click()
    expect(page.locator(".attribution-table")).to_be_visible()
    assert len(set(double.keys)) == 2
    page.close()


def test_late_cancel_of_completed_handle_restores_actual_completed_result(browser, app_server):
    page = browser.new_page()
    double = AttributionDouble(page)
    double.get_status, double.cancel_completed = "running", True
    page.goto(app_server.url + "/#/demo")
    double.analyze()
    page.get_by_role("button", name="Hủy tính toán").click()
    expect(page.locator(".attribution-table")).to_be_visible()
    assert len(double.posts) == 1
    page.close()


@pytest.mark.parametrize("late", [500, 404, "failed"])
def test_old_poll_after_cancel_completed_cannot_erase_validated_result(browser, app_server, late):
    page = browser.new_page()
    double = AttributionDouble(page)
    double.get_status, double.cancel_completed, double.hold_next_get = "running", True, True
    page.goto(app_server.url + "/#/demo")
    double.analyze("Câu giữ kết quả khi hủy muộn.")
    # Wait for the first poll to reach the double, then leave it pending while
    # cancel reports completion and the separate recovery GET is validated.
    for _ in range(100):
        if double.held_gets: break
        page.wait_for_timeout(25)
    assert len(double.held_gets) == 1
    page.get_by_role("button", name="Hủy tính toán").click()
    expect(page.locator(".attribution-table")).to_be_visible()
    expect(page.locator(".quote-text")).to_have_text("Câu giữ kết quả khi hủy muộn.")
    completed_total = page.locator(".total-sign").inner_text()
    route, result = double.held_gets.pop()
    if isinstance(late, int):
        route.fulfill(status=late, json=dict(code="LATE_POLL_ERROR", message="Lỗi poll cũ"))
    else:
        result.update(status="failed", error=dict(code="LATE_POLL_FAILURE", message="Poll cũ failed"))
        route.fulfill(json=result)
    page.wait_for_timeout(1300)
    expect(page.locator(".attribution-table")).to_be_visible()
    expect(page.locator(".total-sign")).to_have_text(completed_total)
    expect(page.locator('.contribution-layout')).to_have_attribute('data-attribution-id', 'attr1')
    expect(page.locator("#word-analysis .notice.error")).to_have_count(0)
    expect(page.locator("#sentiment")).to_be_visible()
    assert len(double.jobs) == len(double.posts) == 1 and len(double.gets) == 2
    assert double.cancels == ["attr1"]
    page.close()


@pytest.mark.parametrize("defect", ["source","hash","identity","target","span","partition","token-order","sum","nan","grapheme"])
def test_invalid_completed_payload_never_renders_zero_or_wrong_words(browser, app_server, defect):
    page = browser.new_page()
    double = AttributionDouble(page, group_count=2 if defect == "token-order" else 1)
    def mutate(result):
        if defect == "source": result["source"]["source_job_id"] = "other-job"
        elif defect == "hash": result["source"]["text_hash"] = "0"*64
        elif defect == "identity": result["source"]["execution_identity"] = dict(result["source"]["execution_identity"], manifest_sha256="c"*64)
        elif defect == "target": result["method"]["target"] = dict(kind="label_score", label_id=3)
        elif defect == "span": result["groups"][0]["text"] = "Câu cũ"
        elif defect == "partition": result["groups"][0]["token_indices"] = [0]
        elif defect == "token-order":
            result["groups"][0]["token_indices"], result["groups"][1]["token_indices"] = result["groups"][1]["token_indices"], result["groups"][0]["token_indices"]
        elif defect == "sum": result["aggregate"]["total_contribution"] += 1
        elif defect == "nan": result["groups"][0]["contribution"] = None
        else:
            result["groups"][0]["end_utf16"] = 6
            result["groups"][0]["text"] = "Tốt 👍"
    double.mutate = mutate
    page.goto(app_server.url + "/#/demo")
    double.analyze("Tốt 👍🏽 nhưng còn lỗi.")
    expect(page.locator("#word-analysis .notice.error")).to_contain_text("không khớp nguồn")
    expect(page.locator(".attribution-table")).to_have_count(0)
    expect(page.locator("#sentiment")).to_be_visible()
    expect(page.locator('#contribution-donut')).to_have_count(0)
    page.close()


@pytest.mark.parametrize("count", [1,6,9,16])
def test_mobile_total_follows_every_row_expand_collapse_and_raw_snapshot(browser, app_server, count):
    page = browser.new_page(viewport=dict(width=390,height=844))
    double = AttributionDouble(page, group_count=count)
    page.goto(app_server.url + "/#/demo")
    text = " ".join(f"cụm{i}" for i in range(count))
    double.analyze("  " + text + "  ")
    expect(page.locator(".quote-text")).to_have_text(text)
    def check():
        total = page.locator(".total-cell").bounding_box()
        rows = page.locator(".weight-cell")
        assert total and all((box := rows.nth(i).bounding_box()) and box["y"] + box["height"] <= total["y"] + 1 for i in range(rows.count()))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator(".remaining-row .weight-meter").count() == 0
    check()
    if count > 6:
        page.get_by_role("button", name="Xem đủ", exact=True).click()
        expect(page.locator(".phrase-button")).to_have_count(count)
        check()
        page.get_by_role("button", name="Thu gọn lại 6 từ chính").click()
        expect(page.locator(".phrase-button")).to_have_count(6)
        check()
    page.close()
