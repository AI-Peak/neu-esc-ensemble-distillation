"""Regression tests for post-review findings R1, R2, and R3 (Three-Layer Webapp Demo).

Uses a lightweight `GatedControlledRegistry` subclass of `ControlledE2ERegistry`
with file-based runtime synchronization flags (`pair_gate.lock`, `pair_entered.flag`,
`pair_fail_once.flag`, `model_identity_v2.flag`) so worker/job states (`queued`,
`running`, `failed -> retry`, `MODEL_IDENTITY_CHANGED`) are deterministically proved
without sleep-based race assumptions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

import httpx
import pytest
from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.e2e.react_callbacks import invoke_bound_onclick, settle_browser
from tests.e2e.test_three_layer_demo import (
    ControlledE2ERegistry,
    ControlledTestServer,
    M3_PAIR_INVALID_TEXT,
    M3_REPEAT_TEXT,
    M3_SECOND_ITEM_TEXT,
    M3_SWITCH_TEXT,
    PROFILES,
    _assert_expected_console_only,
    _utf16_span,
    assert_no_horizontal_overflow,
    prepare_screenshot,
    track_errors,
    wait_for_run_terminal,
)

M3_FAIL_ONCE_TEXT = "M3: Văn bản lỗi lần đầu [PAIR_FAIL_ONCE] để thử lại."
M3_REV2_TEXT = "M3: Văn bản phiên bản 2 có dự đoán mới."
M3_BLOCKER_TEXT = "M3: Văn bản giữ worker bận để kiểm tra hàng chờ."
R1_B_TEXT = "Câu 1 kiểm tra refetch nền."

_GATED_CLEAR_SENT_POS = {
    "label_id": 1,
    "scores": [0.05, 0.85, 0.05, 0.05],
}
_GATED_CLEAR_SENT_NEG = {
    "label_id": 2,
    "scores": [0.05, 0.05, 0.85, 0.05],
}
_GATED_CLEAR_TOPIC_4 = {
    "label_id": 4,
    "scores": [0.01, 0.01, 0.01, 0.01, 0.82, 0.01, 0.01, 0.01, 0.01, 0.10],
}
_GATED_CLEAR_TOPIC_2 = {
    "label_id": 2,
    "scores": [0.01, 0.01, 0.82, 0.01, 0.10, 0.01, 0.01, 0.01, 0.01, 0.01],
}

GATED_EXTRA_SIGNAL_SPECS = {
    ("neu", M3_FAIL_ONCE_TEXT): {
        "sentiment": _GATED_CLEAR_SENT_POS,
        "topic": _GATED_CLEAR_TOPIC_4,
    },
    ("neu", M3_REV2_TEXT): {
        "sentiment": _GATED_CLEAR_SENT_NEG,
        "topic": _GATED_CLEAR_TOPIC_2,
    },
    ("neu", M3_BLOCKER_TEXT): {
        "sentiment": _GATED_CLEAR_SENT_POS,
        "topic": _GATED_CLEAR_TOPIC_4,
    },
    ("neu", R1_B_TEXT): {
        "sentiment": _GATED_CLEAR_SENT_POS,
        "topic": _GATED_CLEAR_TOPIC_4,
    },
}


class GatedControlledRegistry(ControlledE2ERegistry):
    """Lightweight subclass of ControlledE2ERegistry with runtime file-flag gates."""

    __test__ = False

    def __init__(self, runtime_dir):
        self.runtime = Path(runtime_dir)

    def status(self, profile):
        base = super().status(profile)
        if (self.runtime / "model_identity_v2.flag").exists():
            return {**base, "model_version": "software-test-double-v2"}
        return base

    def execution_identity(self, profile):
        ident = super().execution_identity(profile)
        if (self.runtime / "model_identity_v2.flag").exists():
            return {**ident, "model_version": "software-test-double-v2"}
        return ident

    def _build_prediction(self, profile, item, spec_override=None):
        if spec_override is None:
            spec_override = GATED_EXTRA_SIGNAL_SPECS.get((profile, item["text"]))
        return super()._build_prediction(profile, item, spec_override=spec_override)

    def predict_pair(self, profile, items, expected_identity):
        texts = (items[0]["text"], items[1]["text"])
        gate_lock = self.runtime / "pair_gate.lock"
        if gate_lock.exists():
            (self.runtime / "pair_entered.flag").write_text("entered", encoding="utf-8")
            deadline = time.monotonic() + 25.0
            while gate_lock.exists() and time.monotonic() < deadline:
                time.sleep(0.02)

        fail_flag = self.runtime / "pair_fail_once.flag"
        if any("[PAIR_FAIL_ONCE]" in t for t in texts) and fail_flag.exists():
            fail_flag.unlink(missing_ok=True)
            identity = self.execution_identity(profile)
            first_pred = self._build_prediction(
                profile,
                items[0],
                spec_override=GATED_EXTRA_SIGNAL_SPECS[("neu", M3_FAIL_ONCE_TEXT)],
            )
            return {
                "predictions": [first_pred],
                "execution_identity": identity,
                "model_input_equal": False,
            }

        return super().predict_pair(profile, items, expected_identity)


class GatedTestServer(ControlledTestServer):
    __test__ = False

    def start(self):
        args = [
            sys.executable,
            __file__,
            "--serve-gated",
            "--runtime",
            str(self.runtime),
            "--port",
            str(self.port),
        ]
        with self.log_path.open("ab") as log:
            self.process = subprocess.Popen(
                args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT
            )
        for _ in range(200):
            if self.process.poll() is not None:
                raise RuntimeError(
                    "Gated E2E API exited early: "
                    + self.log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                )
            try:
                if httpx.get(self.url + "/api/v1/health", timeout=0.5).is_success:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self.stop()
        raise TimeoutError("Gated E2E API did not become ready")


@pytest.fixture
def gated_server(tmp_path):
    server = GatedTestServer(tmp_path / "gated-e2e-runtime").start()
    yield server
    for flag_name in (
        "pair_gate.lock",
        "pair_entered.flag",
        "pair_fail_once.flag",
        "model_identity_v2.flag",
    ):
        (server.runtime / flag_name).unlink(missing_ok=True)
    server.stop()


def _wait_flag(path: Path, timeout_seconds=15.0):
    deadline = time.monotonic() + timeout_seconds
    while not path.exists():
        assert time.monotonic() < deadline, f"Timed out waiting for flag {path}"
        time.sleep(0.02)


def _wait_job_terminal(client, job_id, timeout_seconds=15.0):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in (
            "completed",
            "completed_with_errors",
            "failed",
            "cancelled",
            "interrupted",
        ):
            return job
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not reach terminal state within {timeout_seconds}s")


def _reconnect_and_refetch_item(page, item_id):
    page.wait_for_timeout(3100)
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    with page.expect_response(
        lambda r: r.request.method == "GET"
        and r.url.split("?")[0].endswith(f"/api/v1/items/{item_id}")
    ):
        page.evaluate("window.dispatchEvent(new Event('online'))")


def _create_sensitivity_job_api(client, item, needle):
    start_u16, end_u16 = _utf16_span(item["text"], needle)
    resp = client.post(
        f"/items/{item['id']}/sensitivity-experiments",
        json={
            "revision_id": item["revision_id"],
            "expected_revision": item["revision"],
            "text_sha256": hashlib.sha256(item["text"].encode("utf-8")).hexdigest(),
            "run_id": None,
            "source_prediction_id": item["prediction"]["id"] if item["prediction"] else None,
            "selection": {
                "start_utf16": start_u16,
                "end_utf16": end_u16,
                "text": needle,
            },
        },
        headers={"Idempotency-Key": f"gated-{item['id']}-{time.monotonic_ns()}"},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# R1: Review draft input revision preservation & explicit resolution
# ---------------------------------------------------------------------------


def test_r1_a_409_revision_conflict_preserves_draft_blocks_save_and_prevents_silent_rebase(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R1-A 409 Revision Conflict",
            "profile": "neu",
            "items": [
                {"text": "Dich vu rat tot."},
                {"text": "Phan hoi thu hai cho nut luu va tiep."},
            ],
        },
    ).json()
    item = client.get(f"/datasets/{ds['id']}/items").json()["items"][0]

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    put_requests = []
    page.on(
        "request",
        lambda req: put_requests.append(req.post_data_json)
        if req.method == "PUT" and f"/api/v1/items/{item['id']}/review" in req.url
        else None,
    )

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name="Dich vu rat tot.", exact=True).click()
    detail = page.locator("dialog.detail-panel")
    expect(detail).to_be_visible()

    draft_note = "Draft for original positive text"
    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("1")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(draft_note)

    patch_resp = client.patch(
        f"/items/{item['id']}/text",
        json={"text": "Dich vu rat te.", "expected_revision": 1},
    )
    assert patch_resp.status_code == 200

    save_btn = detail.get_by_role("button", name="Lưu cảm xúc", exact=True)
    save_next_btn = detail.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True)

    with page.expect_response(
        lambda r: r.request.method == "GET" and f"/api/v1/items/{item['id']}" in r.url and r.ok
    ):
        with page.expect_response(
            lambda r: r.request.method == "PUT" and f"/api/v1/items/{item['id']}/review" in r.url
        ) as put_resp:
            save_btn.click()
        assert put_resp.value.status == 409

    # Only 1 PUT must have been issued (no automatic rebase + second PUT).
    assert len(put_requests) == 1
    assert put_requests[0]["expected_revision"] == 1

    conflict = detail.get_by_test_id("review-conflict-sentiment")
    expect(conflict).to_be_visible()
    expect(conflict).to_have_attribute("role", "alert")
    expect(conflict).to_contain_text("1")
    expect(conflict).to_contain_text("2")
    expect(conflict).to_contain_text("Dich vu rat tot.")
    expect(conflict).to_contain_text("Dich vu rat te.")

    # Draft values remain untouched for comparison.
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("corrected")
    expect(detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True)).to_have_value("1")
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(
        draft_note
    )

    # UI dispatch is disabled; separately invoke each current bound callback to test guards.
    expect(save_btn).to_be_disabled()
    expect(save_next_btn).to_be_disabled()
    invoke_bound_onclick(save_btn, disabled=True)
    assert len(put_requests) == 1, "Save callback must not PUT while conflicted"
    invoke_bound_onclick(save_next_btn, disabled=True)
    page.wait_for_timeout(200)
    assert len(put_requests) == 1
    expect(detail).to_contain_text("Dich vu rat te.")
    expect(detail.locator("#detail-title")).to_have_text(f"Dòng {item['source_row']}")
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("corrected")
    expect(detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True)).to_have_value("1")
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(draft_note)
    expect(conflict).to_be_visible()

    # Backend remains untouched (no review saved on rev 2).
    api_item = client.get(f"/items/{item['id']}").json()
    assert api_item["revision"] == 2
    assert api_item["reviews"]["sentiment"] is None
    assert client.get(f"/items/{item['id']}/reviews").json() == []

    _assert_expected_console_only(page_errors, console_errors, ("status of 409",))
    context.close()
    client.close()


def test_r1_b_background_refetch_and_sensitivity_reload_conflict_with_independent_tasks(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R1-B Background Refetch & Sensitivity Reload",
            "profile": "neu",
            "items": [
                {"text": "Câu 1 kiểm tra refetch nền."},
                {"text": M3_SWITCH_TEXT},
            ],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])
    items = client.get(f"/datasets/{ds['id']}/items").json()["items"]
    item1, item2 = items[0], items[1]

    # Seed saved reviews on rev 1 for item 1 so untouched topic must cleanly reset to rev 2.
    for task, label_id in (("sentiment", 1), ("topic", 4)):
        res = client.put(
            f"/items/{item1['id']}/review",
            json={
                "task": task,
                "status": "corrected",
                "label_id": label_id,
                "note": f"Saved rev 1 {task}",
                "expected_revision": 1,
                "expected_review_revision": 0,
            },
        )
        assert res.status_code == 200, res.text

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    detail = page.locator("dialog.detail-panel")

    # Part 1: Background reconnect refetch brings rev 2 before Save is ever clicked.
    page.get_by_role("button", name="Câu 1 kiểm tra refetch nền.", exact=True).click()
    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("2")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Nháp cảm xúc từ rev 1"
    )

    assert (
        client.patch(
            f"/items/{item1['id']}/text",
            json={"text": "Câu 1 đã đổi sang bản 2.", "expected_revision": 1},
        ).status_code
        == 200
    )
    _reconnect_and_refetch_item(page, item1["id"])

    expect(detail).to_contain_text("Phiên bản 2")
    expect(detail.get_by_test_id("review-conflict-sentiment")).to_be_visible()
    expect(detail.get_by_test_id("review-conflict-topic")).to_have_count(0)
    expect(detail.get_by_label("Trạng thái chủ đề", exact=True)).to_have_value("unreviewed")
    expect(detail.get_by_role("textbox", name="Ghi chú chủ đề", exact=True)).to_have_value("")
    expect(detail.get_by_role("button", name="Lưu cảm xúc", exact=True)).to_be_disabled()
    expect(
        detail.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True)
    ).to_be_disabled()

    # Independent non-conflicted topic task CAN still be edited and saved on rev 2.
    detail.get_by_label("Trạng thái chủ đề", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn chủ đề đã sửa", exact=True).select_option("2")
    detail.get_by_role("textbox", name="Ghi chú chủ đề", exact=True).fill(
        "Chủ đề độc lập trên rev 2"
    )
    topic_save = detail.get_by_role("button", name="Lưu chủ đề", exact=True)
    expect(topic_save).to_be_enabled()
    topic_save.click()
    expect(detail.get_by_test_id("review-topic")).to_contain_text("Đã lưu · bản duyệt 1")
    # Sentiment must STILL remain conflicted and locked after topic save!
    expect(detail.get_by_test_id("review-conflict-sentiment")).to_be_visible()
    expect(detail.get_by_role("button", name="Lưu cảm xúc", exact=True)).to_be_disabled()
    expect(
        detail.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True)
    ).to_be_disabled()

    item1_api = client.get(f"/items/{item1['id']}").json()
    assert item1_api["reviews"]["topic"]["label_id"] == 2
    assert item1_api["reviews"]["topic"]["note"] == "Chủ đề độc lập trên rev 2"
    assert item1_api["reviews"]["sentiment"] is None
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # Part 2: Sensitivity 409 REVISION_CONFLICT -> "Tải lại phản hồi" triggers same durable conflict.
    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("0")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Nháp trước reload từ sensitivity"
    )
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "rất tốt"
    )

    assert (
        client.patch(
            f"/items/{item2['id']}/text",
            json={"text": "M3 switch sửa sang bản 2.", "expected_revision": 1},
        ).status_code
        == 200
    )
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    reload_btn = detail.get_by_role("button", name="Tải lại phản hồi", exact=True)
    expect(reload_btn).to_be_visible()
    reload_btn.click()

    expect(detail).to_contain_text("Phiên bản 2")
    expect(detail.get_by_test_id("review-conflict-sentiment")).to_be_visible()
    expect(detail.get_by_role("button", name="Lưu cảm xúc", exact=True)).to_be_disabled()
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(
        "Nháp trước reload từ sensitivity"
    )

    _assert_expected_console_only(page_errors, console_errors, ("status of 409",))
    context.close()
    client.close()


def test_r1_c_zero_review_revisions_input_conflict_enables_resolve_buttons(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R1-C Review Rev 0 vs 0",
            "profile": "neu",
            "items": [{"text": "Bản 1 chưa từng lưu review."}],
        },
    ).json()
    item = client.get(f"/datasets/{ds['id']}/items").json()["items"][0]

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")

    page.get_by_role("button", name="Bản 1 chưa từng lưu review.", exact=True).click()
    detail = page.locator("dialog.detail-panel")
    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("0")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Nháp rev 0 vs rev 0"
    )

    assert (
        client.patch(
            f"/items/{item['id']}/text",
            json={"text": "Bản 2 cũng chưa từng lưu review.", "expected_revision": 1},
        ).status_code
        == 200
    )

    with page.expect_response(
        lambda r: r.request.method == "GET" and f"/api/v1/items/{item['id']}" in r.url and r.ok
    ):
        with page.expect_response(
            lambda r: r.request.method == "PUT" and "/review" in r.url
        ) as put_resp:
            detail.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
        assert put_resp.value.status == 409

    conflict = detail.get_by_test_id("review-conflict-sentiment")
    expect(conflict).to_be_visible()
    expect(conflict).not_to_contain_text("Đang tải bản server mới")
    expect(conflict).to_contain_text("Chưa rà soát")

    discard_btn = detail.get_by_role(
        "button", name="Dùng bản hiện tại, bỏ nháp: cảm xúc", exact=True
    )
    apply_btn = detail.get_by_role(
        "button", name="Áp nháp lên văn bản hiện tại: cảm xúc", exact=True
    )
    expect(discard_btn).to_be_visible()
    expect(discard_btn).to_be_enabled()
    expect(apply_btn).to_be_visible()
    expect(apply_btn).to_be_enabled()

    # Same-revision conflict buttons must not be rendered for cross-input-revision conflict.
    assert (
        detail.get_by_role("button", name="Tải bản server: cảm xúc", exact=True).count()
        == 0
    )
    assert (
        detail.get_by_role("button", name="Áp lại bản nháp: cảm xúc", exact=True).count()
        == 0
    )

    _assert_expected_console_only(page_errors, console_errors, ("status of 409",))
    context.close()
    client.close()


def test_r1_d_explicit_apply_draft_then_save_updates_only_resolved_task(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R1-D Explicit Apply & Save",
            "profile": "neu",
            "items": [{"text": "Văn bản gốc cho R1-D."}],
        },
    ).json()
    item = client.get(f"/datasets/{ds['id']}/items").json()["items"][0]

    # Seed saved topic review on rev 1 so rev 2 proves only resolved sentiment changes.
    assert (
        client.put(
            f"/items/{item['id']}/review",
            json={
                "task": "topic",
                "status": "corrected",
                "label_id": 4,
                "note": "Topic rev 1",
                "expected_revision": 1,
                "expected_review_revision": 0,
            },
        ).status_code
        == 200
    )

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    put_payloads = []
    page.on(
        "request",
        lambda req: put_payloads.append(req.post_data_json)
        if req.method == "PUT" and f"/api/v1/items/{item['id']}/review" in req.url
        else None,
    )

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name="Văn bản gốc cho R1-D.", exact=True).click()
    detail = page.locator("dialog.detail-panel")

    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("1")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Nháp đã đối chiếu R1-D"
    )

    assert (
        client.patch(
            f"/items/{item['id']}/text",
            json={"text": "Văn bản mới cho R1-D.", "expected_revision": 1},
        ).status_code
        == 200
    )
    _reconnect_and_refetch_item(page, item["id"])

    expect(detail.get_by_test_id("review-conflict-sentiment")).to_be_visible()
    save_btn = detail.get_by_role("button", name="Lưu cảm xúc", exact=True)
    expect(save_btn).to_be_disabled()

    # Clicking explicit Apply updates local draft base without sending PUT.
    detail.get_by_role(
        "button", name="Áp nháp lên văn bản hiện tại: cảm xúc", exact=True
    ).click()
    page.wait_for_timeout(150)
    assert put_payloads == []
    expect(detail.get_by_test_id("review-conflict-sentiment")).to_have_count(0)
    expect(save_btn).to_be_enabled()
    expect(
        detail.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True)
    ).to_be_enabled()
    assert client.get(f"/items/{item['id']}").json()["reviews"]["sentiment"] is None

    with page.expect_response(
        lambda r: r.request.method == "PUT" and "/review" in r.url and r.ok
    ):
        save_btn.click()

    assert len(put_payloads) == 1
    assert put_payloads[0]["expected_revision"] == 2
    assert put_payloads[0]["expected_review_revision"] == 0
    assert put_payloads[0]["status"] == "corrected"
    assert put_payloads[0]["label_id"] == 1
    assert put_payloads[0]["note"] == "Nháp đã đối chiếu R1-D"
    assert put_payloads[0]["source_prediction_id"] is None

    expect(detail.get_by_test_id("review-sentiment")).to_contain_text(
        "Đã lưu · bản duyệt 1"
    )

    api_item = client.get(f"/items/{item['id']}").json()
    assert api_item["revision"] == 2
    assert api_item["reviews"]["sentiment"]["status"] == "corrected"
    assert api_item["reviews"]["sentiment"]["label_id"] == 1
    assert api_item["reviews"]["sentiment"]["note"] == "Nháp đã đối chiếu R1-D"
    assert api_item["reviews"]["sentiment"]["source_prediction_id"] is None
    assert api_item["reviews"]["topic"] is None

    history = client.get(f"/items/{item['id']}/reviews").json()
    sent_rev2 = [r for r in history if r["task"] == "sentiment" and r["input_revision"] == 2]
    assert len(sent_rev2) == 1 and sent_rev2[0]["note"] == "Nháp đã đối chiếu R1-D"

    _assert_expected_console_only(page_errors, console_errors)
    context.close()
    client.close()


def test_r1_e_discard_draft_loads_new_revision_server_review_without_saving(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R1-E Discard Draft",
            "profile": "neu",
            "items": [{"text": "Văn bản gốc cho R1-E."}],
        },
    ).json()
    item = client.get(f"/datasets/{ds['id']}/items").json()["items"][0]

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    put_requests = []
    page.on(
        "request",
        lambda req: put_requests.append(req.url)
        if req.method == "PUT" and "/review" in req.url
        else None,
    )

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name="Văn bản gốc cho R1-E.", exact=True).click()
    detail = page.locator("dialog.detail-panel")

    # Dirty BOTH sentiment (will discard) and topic (must stay conflicted independently).
    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("0")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Nháp cảm xúc sẽ bị bỏ"
    )
    detail.get_by_label("Trạng thái chủ đề", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn chủ đề đã sửa", exact=True).select_option("4")
    detail.get_by_role("textbox", name="Ghi chú chủ đề", exact=True).fill(
        "Nháp chủ đề giữ nguyên"
    )

    assert (
        client.patch(
            f"/items/{item['id']}/text",
            json={"text": "Văn bản mới cho R1-E.", "expected_revision": 1},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/items/{item['id']}/review",
            json={
                "task": "sentiment",
                "status": "corrected",
                "label_id": 2,
                "note": "Nhãn server trên rev 2",
                "expected_revision": 2,
                "expected_review_revision": 0,
            },
        ).status_code
        == 200
    )

    _reconnect_and_refetch_item(page, item["id"])

    sent_conflict = detail.get_by_test_id("review-conflict-sentiment")
    topic_conflict = detail.get_by_test_id("review-conflict-topic")
    expect(sent_conflict).to_be_visible()
    expect(sent_conflict).to_contain_text("Nhãn server trên rev 2")
    expect(topic_conflict).to_be_visible()

    detail.get_by_role(
        "button", name="Dùng bản hiện tại, bỏ nháp: cảm xúc", exact=True
    ).click()
    page.wait_for_timeout(150)

    assert put_requests == []
    expect(sent_conflict).to_have_count(0)
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("corrected")
    expect(detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True)).to_have_value("2")
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(
        "Nhãn server trên rev 2"
    )
    expect(detail.get_by_test_id("review-sentiment")).to_contain_text(
        "Đã lưu · bản duyệt 1"
    )
    expect(detail.get_by_role("button", name="Lưu cảm xúc", exact=True)).to_be_disabled()

    # Topic remained untouched by sentiment discard.
    expect(topic_conflict).to_be_visible()
    expect(detail.get_by_role("textbox", name="Ghi chú chủ đề", exact=True)).to_have_value(
        "Nháp chủ đề giữ nguyên"
    )

    _assert_expected_console_only(page_errors, console_errors)
    context.close()
    client.close()


def test_r1_f_confirmed_provenance_cleared_on_cross_revision_apply_and_confirm_locked(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R1-F Confirmed Provenance Across Revisions",
            "profile": "neu",
            "items": [{"text": M3_SWITCH_TEXT}],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])
    item_rev1 = client.get(f"/datasets/{ds['id']}/items").json()["items"][0]
    run1_pred_id = item_rev1["prediction"]["id"]

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")

    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")

    # Positive control: the same callback adapter changes the valid draft on rev 1.
    confirm_sent_btn = detail.get_by_role(
        "button", name="Xác nhận dự đoán đang xem: cảm xúc", exact=True
    )
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("unreviewed")
    expect(confirm_sent_btn).to_be_enabled()
    invoke_bound_onclick(confirm_sent_btn, disabled=False)
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("confirmed")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Xác nhận từ rev 1"
    )
    expect(detail.get_by_test_id("confirmed-label-sentiment")).to_have_text("Tích cực")
    expect(detail.get_by_test_id("confirmed-source-sentiment")).to_contain_text(
        run1_pred_id
    )

    # Patch text to rev 2 AND run Run 2 so rev 2 also has its own distinct prediction!
    assert (
        client.patch(
            f"/items/{item_rev1['id']}/text",
            json={"text": M3_REV2_TEXT, "expected_revision": 1},
        ).status_code
        == 200
    )
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])
    item_rev2 = client.get(f"/items/{item_rev1['id']}").json()
    run2_pred_id = item_rev2["prediction"]["id"]
    assert run2_pred_id != run1_pred_id

    _reconnect_and_refetch_item(page, item_rev1["id"])

    conflict = detail.get_by_test_id("review-conflict-sentiment")
    expect(conflict).to_be_visible()
    expect(conflict).to_contain_text("Tự chọn / sửa nhãn")

    # Disabled UI and direct callback guard both preserve the old draft against rev 2 prediction.
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("confirmed")
    expect(detail.get_by_test_id("confirmed-source-sentiment")).to_contain_text(
        run1_pred_id
    )
    expect(confirm_sent_btn).to_be_disabled()
    invoke_bound_onclick(confirm_sent_btn, disabled=True)
    expect(detail.get_by_test_id("confirmed-source-sentiment")).to_contain_text(
        run1_pred_id
    )
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("confirmed")
    expect(detail.get_by_test_id("confirmed-label-sentiment")).to_have_text("Tích cực")
    expect(detail.get_by_test_id("confirmed-source-sentiment")).not_to_contain_text(run2_pred_id)
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value("Xác nhận từ rev 1")
    expect(conflict).to_be_visible()

    # Explicit apply converts confirmed -> corrected, clears source_prediction_id, keeps label & note.
    detail.get_by_role(
        "button", name="Áp nháp lên văn bản hiện tại: cảm xúc", exact=True
    ).click()
    expect(conflict).to_have_count(0)
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("corrected")
    expect(detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True)).to_have_value("1")
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(
        "Xác nhận từ rev 1"
    )
    expect(detail.get_by_test_id("confirmed-source-sentiment")).to_have_count(0)

    detail.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    expect(detail.get_by_test_id("review-sentiment")).to_contain_text(
        "Đã lưu · bản duyệt 1"
    )

    api_after = client.get(f"/items/{item_rev1['id']}").json()
    assert api_after["reviews"]["sentiment"]["status"] == "corrected"
    assert api_after["reviews"]["sentiment"]["label_id"] == 1
    assert api_after["reviews"]["sentiment"]["note"] == "Xác nhận từ rev 1"
    assert api_after["reviews"]["sentiment"]["source_prediction_id"] is None
    assert api_after["review_signals"]["sentiment"]["review_relation"] == "manual"

    # After conflict is resolved, confirming rev 2's displayed prediction works again.
    expect(confirm_sent_btn).to_be_enabled()

    _assert_expected_console_only(page_errors, console_errors)
    context.close()
    client.close()


def test_r1_g_same_input_revision_review_conflict_preserves_confirmed_provenance(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R1-G Same Input Revision Provenance",
            "profile": "neu",
            "items": [{"text": M3_SWITCH_TEXT}],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])
    item_r1 = client.get(f"/datasets/{ds['id']}/items").json()["items"][0]
    run1_pred_id = item_r1["prediction"]["id"]

    # Seed confirmed review from Run 1.
    assert (
        client.put(
            f"/items/{item_r1['id']}/review",
            json={
                "task": "sentiment",
                "status": "confirmed",
                "label_id": item_r1["prediction"]["sentiment"]["label_id"],
                "source_prediction_id": run1_pred_id,
                "note": "Confirmed Run 1",
                "expected_revision": 1,
                "expected_review_revision": 0,
            },
        ).status_code
        == 200
    )

    # Create Run 2 on the SAME input revision 1.
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")

    # Edit note only on confirmed review (keeps run1_pred_id across Run 2).
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Sửa ghi chú từ tab A"
    )
    expect(detail.get_by_test_id("confirmed-source-sentiment")).to_contain_text(
        run1_pred_id
    )

    # Another tab saves a conflicting review on the SAME input revision 1.
    assert (
        client.put(
            f"/items/{item_r1['id']}/review",
            json={
                "task": "sentiment",
                "status": "corrected",
                "label_id": 2,
                "note": "Tab B sửa cùng rev 1",
                "expected_revision": 1,
                "expected_review_revision": 1,
            },
        ).status_code
        == 200
    )

    with page.expect_response(
        lambda r: r.request.method == "PUT" and "/review" in r.url
    ) as conflict_resp:
        detail.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    assert conflict_resp.value.status == 409

    conflict = detail.get_by_test_id("review-conflict-sentiment")
    expect(conflict).to_be_visible()
    expect(conflict).to_contain_text("Tab B sửa cùng rev 1")

    # Same-input-revision conflict keeps old buttons and preserves confirmed provenance!
    reapply_btn = detail.get_by_role("button", name="Áp lại bản nháp: cảm xúc", exact=True)
    expect(reapply_btn).to_be_enabled()
    reapply_btn.click()

    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("confirmed")
    expect(detail.get_by_test_id("confirmed-source-sentiment")).to_contain_text(
        run1_pred_id
    )

    detail.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    expect(detail.get_by_test_id("review-sentiment")).to_contain_text(
        "Đã lưu · bản duyệt 3"
    )

    saved = client.get(f"/items/{item_r1['id']}").json()["reviews"]["sentiment"]
    assert saved["status"] == "confirmed"
    assert saved["label_id"] == 1
    assert saved["note"] == "Sửa ghi chú từ tab A"
    assert saved["source_prediction_id"] == run1_pred_id

    _assert_expected_console_only(page_errors, console_errors, ("status of 409",))
    context.close()
    client.close()


def test_r1_h_failed_refetch_after_409_and_rev3_after_resolve_keep_lock(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R1-H Failed Refetch & Rev 3",
            "profile": "neu",
            "items": [{"text": "Văn bản bản 1 R1-H."}],
        },
    ).json()
    item = client.get(f"/datasets/{ds['id']}/items").json()["items"][0]

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    put_requests = []
    page.on(
        "request",
        lambda req: put_requests.append(req.post_data_json)
        if req.method == "PUT" and "/review" in req.url
        else None,
    )

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name="Văn bản bản 1 R1-H.", exact=True).click()
    detail = page.locator("dialog.detail-panel")

    draft_note = "Nháp giữ qua refetch lỗi và rev 3"
    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("1")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(draft_note)

    # Patch to rev 2 out-of-band, then fail GET /items/{id} with 500 during refresh after 409.
    assert (
        client.patch(
            f"/items/{item['id']}/text",
            json={"text": "Văn bản bản 2 R1-H.", "expected_revision": 1},
        ).status_code
        == 200
    )

    failed_get_count = []

    def fail_item_get(route):
        if route.request.method == "GET" and route.request.url.split("?")[0].endswith(
            f"/api/v1/items/{item['id']}"
        ):
            failed_get_count.append(route.request.url)
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"code": "ITEM_GET_500", "message": "Lỗi tải bản mới."}),
            )
        else:
            route.continue_()

    page.route(f"**/api/v1/items/{item['id']}*", fail_item_get)

    save_btn = detail.get_by_role("button", name="Lưu cảm xúc", exact=True)
    save_next_btn = detail.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True)
    with page.expect_response(
        lambda r: r.request.method == "PUT" and "/review" in r.url
    ) as put_409:
        save_btn.click()
    assert put_409.value.status == 409

    conflict = detail.get_by_test_id("review-conflict-sentiment")
    retry_fetch_btn = conflict.get_by_role("button", name="Thử tải bản hiện tại", exact=True)
    expect(conflict).to_be_visible()
    expect(retry_fetch_btn).to_be_visible(timeout=10000)
    assert len(failed_get_count) >= 1

    discard_btn = detail.get_by_role(
        "button", name="Dùng bản hiện tại, bỏ nháp: cảm xúc", exact=True
    )
    apply_btn = detail.get_by_role(
        "button", name="Áp nháp lên văn bản hiện tại: cảm xúc", exact=True
    )
    # Without a loaded snapshot, disabled UI and the bound Save callbacks both block writes.
    expect(discard_btn).to_be_disabled()
    expect(apply_btn).to_be_disabled()
    expect(save_btn).to_be_disabled()
    expect(save_next_btn).to_be_disabled()
    invoke_bound_onclick(save_btn, disabled=True)
    assert len(put_requests) == 1, "Save callback must not PUT while conflicted"
    invoke_bound_onclick(save_next_btn, disabled=True)
    page.wait_for_timeout(200)
    assert len(put_requests) == 1
    expect(detail.locator("#detail-title")).to_have_text(f"Dòng {item['source_row']}")
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("corrected")
    expect(detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True)).to_have_value("1")
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(draft_note)
    expect(conflict).to_be_visible()
    expect(apply_btn).to_be_disabled()
    expect(discard_btn).to_be_disabled()

    # Restore GET and click "Thử tải bản hiện tại" -> loads rev 2 snapshot and enables resolve.
    page.unroute(f"**/api/v1/items/{item['id']}*", fail_item_get)
    with page.expect_response(
        lambda r: r.request.method == "GET"
        and r.url.split("?")[0].endswith(f"/api/v1/items/{item['id']}")
        and r.ok
    ):
        retry_fetch_btn.click()

    expect(detail).to_contain_text("Phiên bản 2")
    expect(apply_btn).to_be_enabled()
    expect(discard_btn).to_be_enabled()
    apply_btn.click()
    expect(save_btn).to_be_enabled()

    # Before clicking Save, rev 3 appears out-of-band -> Save hits 409 again without auto-retry!
    assert (
        client.patch(
            f"/items/{item['id']}/text",
            json={"text": "Văn bản bản 3 R1-H.", "expected_revision": 2},
        ).status_code
        == 200
    )

    with page.expect_response(
        lambda r: r.request.method == "GET"
        and r.url.split("?")[0].endswith(f"/api/v1/items/{item['id']}")
        and r.ok
    ):
        with page.expect_response(
            lambda r: r.request.method == "PUT" and "/review" in r.url
        ) as put_rev3_409:
            save_btn.click()
        assert put_rev3_409.value.status == 409

    assert len(put_requests) == 2
    assert put_requests[1]["expected_revision"] == 2
    expect(detail).to_contain_text("Phiên bản 3")
    expect(conflict).to_be_visible()
    expect(conflict).to_contain_text("2")
    expect(conflict).to_contain_text("3")
    expect(save_btn).to_be_disabled()

    apply_btn.click()
    save_btn.click()
    expect(detail.get_by_test_id("review-sentiment")).to_contain_text(
        "Đã lưu · bản duyệt 1"
    )

    api_final = client.get(f"/items/{item['id']}").json()
    assert api_final["revision"] == 3
    assert api_final["reviews"]["sentiment"]["note"] == draft_note

    _assert_expected_console_only(
        page_errors, console_errors, ("status of 409", "status of 500")
    )
    context.close()
    client.close()


def test_r1_negative_control_clean_save_and_historical_stale_locked(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R1 Negative Control",
            "profile": "neu",
            "items": [
                {"text": M3_SWITCH_TEXT},
                {"text": M3_SECOND_ITEM_TEXT},
            ],
        },
    ).json()
    run1 = client.post("/analysis-runs", json={"dataset_id": ds["id"]}).json()
    wait_for_run_terminal(client, ds["id"])
    items = client.get(f"/datasets/{ds['id']}/items").json()["items"]

    # Edit item 2 to rev 2 so historical Run 1 view marks it stale.
    assert (
        client.patch(
            f"/items/{items[1]['id']}/text",
            json={"text": "M3 câu 2 đã sửa sang bản 2.", "expected_revision": 1},
        ).status_code
        == 200
    )

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")

    # Normal clean save without conflict works in 1 click.
    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")
    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("confirmed")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill("Lưu bình thường")
    # Positive control: invoking the same adapter on a valid Save sends exactly one PUT.
    save_requests = []
    page.on("request", lambda req: save_requests.append(req.post_data_json)
            if req.method == "PUT" and "/review" in req.url else None)
    with page.expect_response(lambda r: r.request.method == "PUT" and "/review" in r.url) as saved_response:
        invoke_bound_onclick(detail.get_by_role("button", name="Lưu cảm xúc", exact=True), disabled=False)
    assert saved_response.value.status == 200
    expect(detail.get_by_test_id("review-sentiment")).to_contain_text("Đã lưu · bản duyệt 1")
    assert len(save_requests) == 1
    assert save_requests[0]["status"] == "confirmed"
    assert save_requests[0]["note"] == "Lưu bình thường"
    saved_review = client.get(f"/items/{items[0]['id']}").json()["reviews"]["sentiment"]
    assert saved_review["source_prediction_id"] == items[0]["prediction"]["id"]
    assert saved_review["note"] == "Lưu bình thường"
    expect(detail.get_by_test_id("review-conflict-sentiment")).to_have_count(0)
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # Historical run view with item.stale=true remains locked for review.
    page.get_by_label("Lần phân tích", exact=True).select_option(run1["id"])
    page.locator("button.text-cell", has_text=M3_SECOND_ITEM_TEXT).click()
    expect(detail).to_contain_text("Văn bản đã thay đổi sau lần phân tích này.")
    expect(detail.get_by_test_id("review-sentiment")).to_have_attribute("disabled", "")
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_be_disabled()
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_be_disabled()
    expect(detail.get_by_role("button", name="Lưu cảm xúc", exact=True)).to_be_disabled()
    expect(
        detail.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True)
    ).to_be_disabled()

    _assert_expected_console_only(page_errors, console_errors)
    context.close()
    client.close()


# ---------------------------------------------------------------------------
# R2: Polling error keeps job ID & cancel capability until terminal/404
# ---------------------------------------------------------------------------


def test_r2_a_poll_500_close_details_and_dialog_cancels_active_job(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R2-A Poll 500 Close Cancel",
            "profile": "neu",
            "items": [
                {"text": M3_BLOCKER_TEXT},
                {"text": M3_SWITCH_TEXT},
            ],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])
    items = client.get(f"/datasets/{ds['id']}/items").json()["items"]
    blocker_item = next(i for i in items if i["text"] == M3_BLOCKER_TEXT)

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    cancel_urls = []
    page.on(
        "request",
        lambda req: cancel_urls.append(req.url)
        if req.method == "POST" and req.url.endswith("/cancel")
        else None,
    )

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    detail = page.locator("dialog.detail-panel")

    # Part 1: Keep target job deterministically `queued` behind a gated blocker, fail poll 500, close <details>.
    gate_lock = gated_server.runtime / "pair_gate.lock"
    entered_flag = gated_server.runtime / "pair_entered.flag"
    entered_flag.unlink(missing_ok=True)
    gate_lock.write_text("lock", encoding="utf-8")

    blocker_exp = _create_sensitivity_job_api(client, blocker_item, "kiểm tra")
    _wait_flag(entered_flag)
    assert client.get(f"/jobs/{blocker_exp['job_id']}").json()["status"] == "running"

    def fail_poll_500(route):
        if route.request.method == "GET":
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"code": "POLL_500", "message": "Lỗi 500 khi poll thử nghiệm."}),
            )
        else:
            route.continue_()

    page.route("**/api/v1/sensitivity-experiments/*", fail_poll_500)

    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "rất tốt"
    )

    run_btn = detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as created_queued:
        run_btn.click()
    queued_job_id = created_queued.value.json()["job_id"]
    assert client.get(f"/jobs/{queued_job_id}").json()["status"] == "queued"

    expect(detail.get_by_text("Lỗi 500 khi poll thử nghiệm.", exact=True)).to_be_visible(
        timeout=15000
    )
    expect(detail.locator(".sensitivity-status")).to_be_visible()
    expect(detail.locator(".sensitivity-status")).to_contain_text(
        "Không đọc được trạng thái thử nghiệm hiện tại"
    )
    expect(detail.get_by_role("button", name="Hủy thử nghiệm", exact=True)).to_be_enabled()
    expect(run_btn).to_be_disabled()

    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/api/v1/jobs/{queued_job_id}/cancel" in r.url
    ):
        detail.locator("details.sensitivity-panel summary").click()

    assert any(f"/jobs/{queued_job_id}/cancel" in u for u in cancel_urls)
    queued_job_after = client.get(f"/jobs/{queued_job_id}").json()
    assert queued_job_after["status"] == "cancelled"
    assert queued_job_after["cancel_requested"] is True

    # Release blocker and wait for it to finish cleanly.
    gate_lock.unlink(missing_ok=True)
    _wait_job_terminal(client, blocker_exp["job_id"])

    # Re-opening <details> shows reset state and no stale results.
    detail.locator("details.sensitivity-panel summary").click()
    expect(detail.locator(".sensitivity-results")).to_have_count(0)
    expect(
        detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True)
    ).to_have_value("")

    # Part 2: Target job itself is `running` (gated), poll hits 500, close <dialog> ("Đóng chi tiết").
    cancel_urls.clear()
    entered_flag.unlink(missing_ok=True)
    gate_lock.write_text("lock", encoding="utf-8")

    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "rất tốt"
    )
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as created_running:
        run_btn.click()
    running_job_id = created_running.value.json()["job_id"]

    _wait_flag(entered_flag)
    assert client.get(f"/jobs/{running_job_id}").json()["status"] == "running"
    expect(detail.get_by_text("Lỗi 500 khi poll thử nghiệm.", exact=True)).to_be_visible(
        timeout=15000
    )
    expect(detail.locator(".sensitivity-status")).to_be_visible()

    with page.expect_response(
        lambda r: r.request.method == "POST"
        and f"/api/v1/jobs/{running_job_id}/cancel" in r.url
    ):
        detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    assert any(f"/jobs/{running_job_id}/cancel" in u for u in cancel_urls)
    assert client.get(f"/jobs/{running_job_id}").json()["cancel_requested"] is True

    gate_lock.unlink(missing_ok=True)
    terminal = _wait_job_terminal(client, running_job_id)
    assert terminal["status"] == "cancelled"

    page.unroute("**/api/v1/sensitivity-experiments/*", fail_poll_500)
    _assert_expected_console_only(page_errors, console_errors, ("status of 500",))
    context.close()
    client.close()


def test_r2_b_poll_network_abort_context_switch_cancels_and_isolates(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R2-B Network Abort Context Switches",
            "profile": "neu",
            "items": [
                {"text": M3_REPEAT_TEXT},
                {"text": M3_SECOND_ITEM_TEXT},
            ],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])
    items = client.get(f"/datasets/{ds['id']}/items").json()["items"]
    item1 = items[0]

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    cancel_urls = []
    page.on(
        "request",
        lambda req: cancel_urls.append(req.url)
        if req.method == "POST" and req.url.endswith("/cancel")
        else None,
    )

    def abort_poll(route):
        if route.request.method == "GET":
            route.abort()
        else:
            route.continue_()

    page.route("**/api/v1/sensitivity-experiments/*", abort_poll)

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name=M3_REPEAT_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill("tốt")
    radios = detail.locator("fieldset.sensitivity-occurrences input[type='radio']")
    radios.nth(0).check()

    gate_lock = gated_server.runtime / "pair_gate.lock"
    entered_flag = gated_server.runtime / "pair_entered.flag"
    run_btn = detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)

    # 1. Switch occurrence selection while poll is aborted -> cancels job 1.
    entered_flag.unlink(missing_ok=True)
    gate_lock.write_text("lock", encoding="utf-8")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as resp1:
        run_btn.click()
    job1_id = resp1.value.json()["job_id"]
    _wait_flag(entered_flag)
    expect(
        detail.get_by_text(
            "Không thể kết nối dịch vụ local. Kiểm tra API đang chạy rồi thử lại.",
            exact=True,
        )
    ).to_be_visible(timeout=15000)
    expect(detail.locator(".sensitivity-status")).to_be_visible()

    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/api/v1/jobs/{job1_id}/cancel" in r.url
    ):
        radios.nth(1).check()

    gate_lock.unlink(missing_ok=True)
    assert _wait_job_terminal(client, job1_id)["status"] == "cancelled"

    # 2. Switch item ("Lưu và câu tiếp theo →") while poll is aborted -> cancels job 2, no leak into item 2.
    entered_flag.unlink(missing_ok=True)
    gate_lock.write_text("lock", encoding="utf-8")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as resp2:
        run_btn.click()
    job2_id = resp2.value.json()["job_id"]
    _wait_flag(entered_flag)
    expect(detail.locator(".sensitivity-status")).to_be_visible(timeout=15000)

    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/api/v1/jobs/{job2_id}/cancel" in r.url
    ):
        detail.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True).click()

    expect(detail).to_contain_text(M3_SECOND_ITEM_TEXT)
    gate_lock.unlink(missing_ok=True)
    assert _wait_job_terminal(client, job2_id)["status"] == "cancelled"

    detail.locator("details.sensitivity-panel summary").click()
    expect(detail.locator(".sensitivity-results")).to_have_count(0)
    expect(detail.locator(".sensitivity-status")).to_have_count(0)

    # 3. Switch source revision (revision_id changes via refetch) while poll is aborted -> cancels job 3.
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    page.get_by_role("button", name=M3_REPEAT_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill("tốt")
    detail.locator("fieldset.sensitivity-occurrences input[type='radio']").nth(0).check()

    entered_flag.unlink(missing_ok=True)
    gate_lock.write_text("lock", encoding="utf-8")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as resp3:
        run_btn.click()
    job3_id = resp3.value.json()["job_id"]
    _wait_flag(entered_flag)
    expect(detail.locator(".sensitivity-status")).to_be_visible(timeout=15000)

    # Cancel job3 via revision change (first release gate? No! Keep gate so job3 is still running!).
    assert (
        client.patch(
            f"/items/{item1['id']}/text",
            json={"text": "Giảng viên tốt hơn ở phiên bản 2.", "expected_revision": 1},
        ).status_code
        == 200
    )
    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/api/v1/jobs/{job3_id}/cancel" in r.url
    ):
        _reconnect_and_refetch_item(page, item1["id"])

    gate_lock.unlink(missing_ok=True)
    assert _wait_job_terminal(client, job3_id)["status"] == "cancelled"
    expect(detail).to_contain_text("Phiên bản 2")
    expect(detail.locator(".sensitivity-results")).to_have_count(0)

    page.unroute("**/api/v1/sensitivity-experiments/*", abort_poll)
    _assert_expected_console_only(page_errors, console_errors, ("net::ERR_FAILED",))
    context.close()
    client.close()


def test_r2_c_open_panel_poll_error_retry_and_manual_cancel_with_error_recovery(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R2-C Open Panel Poll Error & Manual Cancel",
            "profile": "neu",
            "items": [
                {"text": M3_BLOCKER_TEXT},
                {"text": M3_SWITCH_TEXT},
            ],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])
    items = client.get(f"/datasets/{ds['id']}/items").json()["items"]
    blocker_item = next(i for i in items if i["text"] == M3_BLOCKER_TEXT)

    gate_lock = gated_server.runtime / "pair_gate.lock"
    entered_flag = gated_server.runtime / "pair_entered.flag"
    entered_flag.unlink(missing_ok=True)
    gate_lock.write_text("lock", encoding="utf-8")
    blocker_exp = _create_sensitivity_job_api(client, blocker_item, "kiểm tra")
    _wait_flag(entered_flag)

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    create_posts = []
    cancel_posts = []
    page.on(
        "request",
        lambda req: create_posts.append(req.url)
        if req.method == "POST" and "/sensitivity-experiments" in req.url
        else (
            cancel_posts.append(req.url)
            if req.method == "POST" and req.url.endswith("/cancel")
            else None
        ),
    )

    poll_gets = []

    def fail_poll_500(route):
        if route.request.method == "GET":
            poll_gets.append(route.request.url)
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"code": "POLL_500", "message": "Lỗi 500 poll R2-C."}),
            )
        else:
            route.continue_()

    page.route("**/api/v1/sensitivity-experiments/*", fail_poll_500)

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "rất tốt"
    )

    run_btn = detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as created_resp:
        run_btn.click()
    target_job_id = created_resp.value.json()["job_id"]
    assert len(create_posts) == 1

    expect(detail.get_by_text("Lỗi 500 poll R2-C.", exact=True)).to_be_visible(
        timeout=15000
    )
    assert len(poll_gets) == 2
    expect(run_btn).to_be_disabled()
    expect(detail.locator(".sensitivity-status")).to_be_visible()
    expect(detail.locator(".sensitivity-status")).to_contain_text(
        "Không đọc được trạng thái thử nghiệm hiện tại"
    )

    # ErrorNotice "Thử lại" triggers a poll retry without recreating a new job.
    detail.locator(".sensitivity-result-area").get_by_role(
        "button", name="Thử lại", exact=True
    ).click()
    page.wait_for_timeout(1500)
    assert len(poll_gets) >= 3
    assert len(create_posts) == 1
    expect(run_btn).to_be_disabled()

    # Clicking "Hủy thử nghiệm" when cancel fails shows error in role="alert" and stays retryable.
    def fail_cancel_500(route):
        route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"code": "CANCEL_FAIL", "message": "Lỗi 500 giả lập khi hủy."}),
        )

    page.route("**/api/v1/jobs/*/cancel", fail_cancel_500)
    cancel_btn = detail.get_by_role("button", name="Hủy thử nghiệm", exact=True)
    cancel_btn.click()
    err_alert = detail.locator(".sensitivity-body > p.error-text[role='alert']")
    expect(err_alert).to_be_visible()
    expect(err_alert).to_have_text("Lỗi 500 giả lập khi hủy.")
    expect(cancel_btn).to_be_enabled()
    expect(run_btn).to_be_disabled()

    # Unroute cancel error (keep GET 500 active!): retry cancel -> immediate "cancelled" -> unlocks create!
    page.unroute("**/api/v1/jobs/*/cancel", fail_cancel_500)
    cancel_btn.click()
    expect(detail.get_by_text("Đã hủy thử nghiệm", exact=True)).to_be_visible(
        timeout=10000
    )
    expect(err_alert).to_have_count(0)
    expect(run_btn).to_be_enabled()
    assert client.get(f"/jobs/{target_job_id}").json()["status"] == "cancelled"

    # Closing <details> after immediate cancelled emits NO extra cancel request.
    count_before_close = len(cancel_posts)
    detail.locator("details.sensitivity-panel summary").click()
    page.wait_for_timeout(200)
    assert len(cancel_posts) == count_before_close

    gate_lock.unlink(missing_ok=True)
    _wait_job_terminal(client, blocker_exp["job_id"])
    page.unroute("**/api/v1/sensitivity-experiments/*", fail_poll_500)
    _assert_expected_console_only(page_errors, console_errors, ("status of 500",))
    context.close()
    client.close()


def test_r2_d_poll_recovers_terminal_or_404_and_subsequent_refetch_500_does_not_relock(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R2-D Recovery & Subsequent 500",
            "profile": "neu",
            "items": [{"text": M3_SWITCH_TEXT}],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    cancel_posts = []
    page.on(
        "request",
        lambda req: cancel_posts.append(req.url)
        if req.method == "POST" and req.url.endswith("/cancel")
        else None,
    )

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")
    detail.locator("details.sensitivity-panel summary").click()
    q_input = detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True)
    run_btn = detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)

    # Part 1: Poll 500 -> recovers to `completed` -> subsequent refetch 500 does NOT re-lock or cancel!
    def fail_poll_500(route):
        if route.request.method == "GET":
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"code": "POLL_500", "message": "Lỗi 500 tạm thời."}),
            )
        else:
            route.continue_()

    page.route("**/api/v1/sensitivity-experiments/*", fail_poll_500)
    q_input.fill("rất tốt")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as created1:
        run_btn.click()
    job1_id = created1.value.json()["job_id"]
    _wait_job_terminal(client, job1_id)

    expect(detail.get_by_text("Lỗi 500 tạm thời.", exact=True)).to_be_visible(
        timeout=15000
    )
    expect(detail.locator(".sensitivity-status")).to_be_visible()
    expect(run_btn).to_be_disabled()

    page.unroute("**/api/v1/sensitivity-experiments/*", fail_poll_500)
    detail.locator(".sensitivity-result-area").get_by_role(
        "button", name="Thử lại", exact=True
    ).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=15000)
    expect(run_btn).to_be_enabled()

    # Subsequent refetch 500 AFTER terminal must NOT re-lock create or emit cancel on close!
    refetch_500_hits = []

    def fail_after_terminal(route):
        if route.request.method == "GET":
            refetch_500_hits.append(route.request.url)
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"code": "POST_TERM_500", "message": "Lỗi 500 sau hoàn tất."}),
            )
        else:
            route.continue_()

    page.route("**/api/v1/sensitivity-experiments/*", fail_after_terminal)
    page.wait_for_timeout(3100)
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    page.evaluate("window.dispatchEvent(new Event('online'))")
    deadline = time.monotonic() + 10
    while len(refetch_500_hits) < 2 and time.monotonic() < deadline:
        page.wait_for_timeout(50)
    assert len(refetch_500_hits) >= 2
    expect(run_btn).to_be_enabled()

    detail.locator("details.sensitivity-panel summary").click()
    page.wait_for_timeout(200)
    assert cancel_posts == []
    page.unroute("**/api/v1/sensitivity-experiments/*", fail_after_terminal)

    # Part 2: Poll 500 -> recovers to real `404` (expired temp dataset) -> unlocks create & no cancel on close.
    detail.locator("details.sensitivity-panel summary").click()
    page.route("**/api/v1/sensitivity-experiments/*", fail_poll_500)
    q_input.fill("rất tốt")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as created2:
        run_btn.click()
    job2_id = created2.value.json()["job_id"]
    _wait_job_terminal(client, job2_id)

    expect(detail.get_by_text("Lỗi 500 tạm thời.", exact=True)).to_be_visible(
        timeout=15000
    )
    expect(run_btn).to_be_disabled()

    conn = sqlite3.connect(gated_server.runtime / "workspace.sqlite3", timeout=10.0)
    try:
        conn.execute("UPDATE datasets SET expires_at = 1.0 WHERE temporary = 1")
        conn.commit()
    finally:
        conn.close()

    page.unroute("**/api/v1/sensitivity-experiments/*", fail_poll_500)
    with page.expect_response(
        lambda r: "/sensitivity-experiments/" in r.url and r.status == 404
    ):
        detail.locator(".sensitivity-result-area").get_by_role(
            "button", name="Thử lại", exact=True
        ).click()

    expect(
        detail.get_by_text(
            "Kết quả tạm đã hết hạn hoặc không còn tồn tại; chạy lại nếu cần.",
            exact=True,
        )
    ).to_be_visible()
    expect(run_btn).to_be_enabled()

    # Subsequent refetch 500 AFTER real 404 must NOT relock create, must NOT show active status/cancel button, and closing must NOT cancel!
    refetch_404_500_hits = []

    def fail_after_404(route):
        if route.request.method == "GET":
            refetch_404_500_hits.append(route.request.url)
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"code": "POST_404_500", "message": "Lỗi 500 sau 404."}),
            )
        else:
            route.continue_()

    page.route("**/api/v1/sensitivity-experiments/*", fail_after_404)
    page.wait_for_timeout(3100)
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    page.evaluate("window.dispatchEvent(new Event('online'))")
    deadline = time.monotonic() + 10
    while len(refetch_404_500_hits) < 2 and time.monotonic() < deadline:
        page.wait_for_timeout(50)
    assert len(refetch_404_500_hits) >= 2

    expect(run_btn).to_be_enabled()
    expect(detail.locator(".sensitivity-status")).to_have_count(0)
    expect(detail.get_by_role("button", name="Hủy thử nghiệm", exact=True)).to_have_count(0)

    detail.locator("details.sensitivity-panel summary").click()
    page.wait_for_timeout(200)
    assert cancel_posts == []
    page.unroute("**/api/v1/sensitivity-experiments/*", fail_after_404)

    _assert_expected_console_only(
        page_errors, console_errors, ("status of 500", "status of 404")
    )
    context.close()
    client.close()


def test_r2_negative_control_normal_sensitivity_completes_without_spurious_cancel(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R2 Negative Control",
            "profile": "neu",
            "items": [{"text": M3_SWITCH_TEXT}],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    cancel_posts = []
    page.on(
        "request",
        lambda req: cancel_posts.append(req.url)
        if req.method == "POST" and req.url.endswith("/cancel")
        else None,
    )

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "rất tốt"
    )
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    assert cancel_posts == []

    _assert_expected_console_only(page_errors, console_errors)
    context.close()
    client.close()


# ---------------------------------------------------------------------------
# R3: Delayed / rejected retry cleanup & concurrency guards
# ---------------------------------------------------------------------------


def test_r3_a_delayed_retry_after_close_details_and_close_dialog_cancels_job(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R3-A Delayed Retry Close Cleanup",
            "profile": "neu",
            "items": [{"text": M3_FAIL_ONCE_TEXT}],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    cancel_urls = []
    page.on(
        "request",
        lambda req: cancel_urls.append(req.url)
        if req.method == "POST" and req.url.endswith("/cancel")
        else None,
    )

    fail_flag = gated_server.runtime / "pair_fail_once.flag"
    gate_lock = gated_server.runtime / "pair_gate.lock"

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    detail = page.locator("dialog.detail-panel")

    # Part 1: Close <details> while retry POST is in flight -> cancels retried job on 200.
    fail_flag.write_text("fail-once", encoding="utf-8")
    page.get_by_role("button", name=M3_FAIL_ONCE_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "để thử lại"
    )
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as exp1_resp:
        detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    job1_id = exp1_resp.value.json()["job_id"]
    expect(detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True)).to_be_visible(
        timeout=15000
    )

    held_retries = []

    def hold_retry(route):
        held_retries.append(route)

    page.route("**/api/v1/jobs/*/retry", hold_retry)
    gate_lock.write_text("lock", encoding="utf-8")

    detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True).click()
    deadline = time.monotonic() + 5
    while len(held_retries) == 0 and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert len(held_retries) == 1

    detail.locator("details.sensitivity-panel summary").click()
    expect(detail.locator("details.sensitivity-panel")).not_to_have_attribute("open", "")

    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/api/v1/jobs/{job1_id}/cancel" in r.url
    ):
        held_retries.pop(0).continue_()

    assert any(f"/jobs/{job1_id}/cancel" in u for u in cancel_urls)
    assert client.get(f"/jobs/{job1_id}").json()["cancel_requested"] is True
    gate_lock.unlink(missing_ok=True)
    assert _wait_job_terminal(client, job1_id)["status"] == "cancelled"

    detail.locator("details.sensitivity-panel summary").click()
    expect(detail.locator(".sensitivity-results")).to_have_count(0)

    # Part 2: Close <dialog> ("Đóng chi tiết") while retry POST is in flight -> cancels retried job on 200.
    cancel_urls.clear()
    fail_flag.write_text("fail-once", encoding="utf-8")
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "để thử lại"
    )
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as exp2_resp:
        detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    job2_id = exp2_resp.value.json()["job_id"]
    expect(detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True)).to_be_visible(
        timeout=15000
    )

    gate_lock.write_text("lock", encoding="utf-8")
    detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True).click()
    deadline = time.monotonic() + 5
    while len(held_retries) == 0 and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert len(held_retries) == 1

    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    expect(detail).to_have_count(0)

    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/api/v1/jobs/{job2_id}/cancel" in r.url
    ):
        held_retries.pop(0).continue_()

    assert any(f"/jobs/{job2_id}/cancel" in u for u in cancel_urls)
    assert client.get(f"/jobs/{job2_id}").json()["cancel_requested"] is True
    gate_lock.unlink(missing_ok=True)
    assert _wait_job_terminal(client, job2_id)["status"] == "cancelled"

    page.unroute("**/api/v1/jobs/*/retry", hold_retry)
    _assert_expected_console_only(page_errors, console_errors)
    context.close()
    client.close()


def test_r3_b_delayed_retry_after_selection_and_item_switch_isolates_new_panel(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R3-B Delayed Retry Switch Isolation",
            "profile": "neu",
            "items": [
                {"text": M3_FAIL_ONCE_TEXT},
                {"text": M3_SECOND_ITEM_TEXT},
            ],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    cancel_urls = []
    page.on(
        "request",
        lambda req: cancel_urls.append(req.url)
        if req.method == "POST" and req.url.endswith("/cancel")
        else None,
    )

    fail_flag = gated_server.runtime / "pair_fail_once.flag"
    gate_lock = gated_server.runtime / "pair_gate.lock"
    held_retries = []

    def hold_retry(route):
        held_retries.append(route)

    page.route("**/api/v1/jobs/*/retry", hold_retry)

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    detail = page.locator("dialog.detail-panel")

    # Part 1: Selection change while retry is in flight -> cancels job1 on 200; new selection runs job2 cleanly!
    fail_flag.write_text("fail-once", encoding="utf-8")
    page.get_by_role("button", name=M3_FAIL_ONCE_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    q_input = detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True)
    q_input.fill("lỗi")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as exp1_resp:
        detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    job1_id = exp1_resp.value.json()["job_id"]
    expect(detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True)).to_be_visible(
        timeout=15000
    )

    gate_lock.write_text("lock", encoding="utf-8")
    detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True).click()
    deadline = time.monotonic() + 5
    while len(held_retries) == 0 and time.monotonic() < deadline:
        page.wait_for_timeout(20)

    # Change selection on the same item while retry is held.
    q_input.fill("để thử lại")

    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/api/v1/jobs/{job1_id}/cancel" in r.url
    ):
        held_retries.pop(0).continue_()

    gate_lock.unlink(missing_ok=True)
    assert _wait_job_terminal(client, job1_id)["status"] == "cancelled"

    # Now creating job2 on the new selection succeeds without touching stale job1!
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as exp2_resp:
        detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    assert exp2_resp.value.status == 202
    job2_id = exp2_resp.value.json()["job_id"]
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=15000)
    assert _wait_job_terminal(client, job2_id)["status"] == "completed"

    # Part 2: Switch item ("Lưu và câu tiếp theo →") while retry is in flight AND create job4 on item 2
    # BEFORE job3's retry returns 200 -> cancels job3 ONLY, leaving item 2's job4 running/completed!
    cancel_urls.clear()
    fail_flag.write_text("fail-once", encoding="utf-8")
    q_input.fill("lỗi")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as exp3_resp:
        detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    job3_id = exp3_resp.value.json()["job_id"]
    expect(detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True)).to_be_visible(
        timeout=15000
    )

    gate_lock.write_text("lock", encoding="utf-8")
    detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True).click()
    deadline = time.monotonic() + 5
    while len(held_retries) == 0 and time.monotonic() < deadline:
        page.wait_for_timeout(20)

    detail.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True).click()
    expect(detail).to_contain_text(M3_SECOND_ITEM_TEXT)

    # Open item 2's sensitivity panel and start job4 BEFORE job3's retry returns 200.
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "chuyển câu"
    )
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as exp4_resp:
        detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    assert exp4_resp.value.status == 202
    job4_id = exp4_resp.value.json()["job_id"]

    # Release job3's delayed retry: must cancel job3, NOT job4!
    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/api/v1/jobs/{job3_id}/cancel" in r.url
    ):
        held_retries.pop(0).continue_()

    assert any(f"/jobs/{job3_id}/cancel" in u for u in cancel_urls)
    assert not any(f"/jobs/{job4_id}/cancel" in u for u in cancel_urls)

    gate_lock.unlink(missing_ok=True)
    assert _wait_job_terminal(client, job3_id)["status"] == "cancelled"
    assert _wait_job_terminal(client, job4_id)["status"] == "completed"
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=15000)
    expect(detail.locator(".sensitivity-results")).to_contain_text(M3_SECOND_ITEM_TEXT)

    page.unroute("**/api/v1/jobs/*/retry", hold_retry)
    _assert_expected_console_only(page_errors, console_errors)
    context.close()
    client.close()


def test_r3_c_retry_response_delayed_after_cleanup_cancels_safely(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R3-C Delayed Response After Server Retry",
            "profile": "neu",
            "items": [{"text": M3_FAIL_ONCE_TEXT}],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)

    fail_flag = gated_server.runtime / "pair_fail_once.flag"
    gate_lock = gated_server.runtime / "pair_gate.lock"
    entered_flag = gated_server.runtime / "pair_entered.flag"
    fail_flag.write_text("fail-once", encoding="utf-8")

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name=M3_FAIL_ONCE_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "để thử lại"
    )
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as exp_resp:
        detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    job_id = exp_resp.value.json()["job_id"]
    expect(detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True)).to_be_visible(
        timeout=15000
    )

    # Server receives and executes POST /retry immediately via route.fetch(),
    # but the HTTP 200 response to the browser is held until AFTER cleanup!
    held_responses = []

    def hold_retry_response(route):
        upstream_resp = route.fetch()
        assert upstream_resp.status == 200
        held_responses.append((route, upstream_resp))

    page.route("**/api/v1/jobs/*/retry", hold_retry_response)
    entered_flag.unlink(missing_ok=True)
    gate_lock.write_text("lock", encoding="utf-8")

    detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True).click()
    deadline = time.monotonic() + 5
    while len(held_responses) == 0 and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert len(held_responses) == 1

    # Prove server ALREADY transitioned job to running before browser gets response.
    _wait_flag(entered_flag)
    assert client.get(f"/jobs/{job_id}").json()["status"] == "running"

    # Cleanup runs BEFORE browser receives retry response.
    detail.locator("details.sensitivity-panel summary").click()
    expect(detail.locator("details.sensitivity-panel")).not_to_have_attribute("open", "")

    # Now deliver delayed 200 retry response to browser -> must still cancel job_id!
    route_obj, upstream_resp = held_responses.pop(0)
    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/api/v1/jobs/{job_id}/cancel" in r.url
    ):
        route_obj.fulfill(response=upstream_resp)

    assert client.get(f"/jobs/{job_id}").json()["cancel_requested"] is True
    gate_lock.unlink(missing_ok=True)
    assert _wait_job_terminal(client, job_id)["status"] == "cancelled"

    page.unroute("**/api/v1/jobs/*/retry", hold_retry_response)
    _assert_expected_console_only(page_errors, console_errors)
    context.close()
    client.close()


def test_r3_d_same_generation_retry_double_click_no_self_cancel_and_stale_cache(
    browser, gated_server
):
    gate_lock = gated_server.runtime / "pair_gate.lock"
    entered_flag = gated_server.runtime / "pair_entered.flag"
    fail_flag = gated_server.runtime / "pair_fail_once.flag"
    # Context closure tears down routes/requests even on assertion failure;
    # the fixture owns server teardown. All gates are released in finally.
    with httpx.Client(base_url=gated_server.url + "/api/v1") as client, browser.new_context(
        viewport={"width": 1280, "height": 900}
    ) as context:
        held_snapshots = []
        try:
            ds = client.post(
                "/datasets",
                json={
                    "name": "R3-D Same-Generation Retry",
                    "profile": "neu",
                    "items": [{"text": M3_FAIL_ONCE_TEXT}],
                },
            ).json()
            client.post("/analysis-runs", json={"dataset_id": ds["id"]})
            wait_for_run_terminal(client, ds["id"])
            page = context.new_page()
            page_errors, console_errors = track_errors(page)
            cancel_urls = []
            page.on(
                "request",
                lambda req: cancel_urls.append(req.url)
                if req.method == "POST" and req.url.endswith("/cancel")
                else None,
            )
            fail_flag.write_text("fail-once", encoding="utf-8")
            page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
            page.get_by_role("button", name=M3_FAIL_ONCE_TEXT, exact=True).click()
            detail = page.locator("dialog.detail-panel")
            detail.locator("details.sensitivity-panel summary").click()
            detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
                "để thử lại"
            )
            with page.expect_response(
                lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
            ) as exp_resp:
                detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
            created = exp_resp.value.json()
            job_id = created["job_id"]
            experiment_id = created["experiment_id"]
            experiment_path = f"/api/v1/sensitivity-experiments/{experiment_id}"
            retry_path = f"/api/v1/jobs/{job_id}/retry"
            retry_btn = detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True)
            expect(retry_btn).to_be_visible(timeout=15000)
            assert client.get(f"/jobs/{job_id}").json()["status"] == "failed"

            # Fetch now, before retry: holding a request alone does not capture old data.
            def hold_stale_exp_get(route):
                if (route.request.method == "GET"
                        and route.request.url.split("?")[0].endswith(experiment_path)
                        and not held_snapshots):
                    snapshot = route.fetch()
                    payload = snapshot.json()
                    held_snapshots.append((route, snapshot, payload))
                    assert snapshot.status == 200
                    assert payload["status"] == "failed", payload
                    assert payload["experiment_id"] == experiment_id
                    assert payload["job_id"] == job_id
                else:
                    route.continue_()

            page.route("**" + experiment_path, hold_stale_exp_get)
            page.evaluate("window.dispatchEvent(new Event('offline'))")
            page.evaluate("window.dispatchEvent(new Event('online'))")
            deadline = time.monotonic() + 5
            while not held_snapshots and time.monotonic() < deadline:
                page.wait_for_timeout(20)
            assert len(held_snapshots) == 1, "Expected one failed response captured before retry"
            stale_route, snapshot, captured_payload = held_snapshots[0]
            assert captured_payload["status"] == "failed"
            stale_request = stale_route.request
            retry_requests = []
            held_retries = []

            def hold_retry(route):
                if route.request.method == "POST" and route.request.url.endswith(retry_path):
                    retry_requests.append(route.request)
                    held_retries.append(route)
                else:
                    route.continue_()

            page.route("**" + retry_path, hold_retry)
            entered_flag.unlink(missing_ok=True)
            gate_lock.write_text("lock", encoding="utf-8")
            # Keep same-render double-click coverage: exactly one POST across the whole flow.
            retry_btn.evaluate("el => { el.click(); el.click(); }")
            deadline = time.monotonic() + 5
            while not held_retries and time.monotonic() < deadline:
                page.wait_for_timeout(20)
            page.wait_for_timeout(150)
            assert len(retry_requests) == 1, f"Expected strictly 1 retry POST, got {len(retry_requests)}"
            with page.expect_response(
                lambda r: r.request == retry_requests[0] and r.status == 200
            ) as retry_response:
                held_retries.pop().continue_()
            assert retry_response.value.json()["id"] == job_id
            _wait_flag(entered_flag)
            server_payload = client.get(f"/sensitivity-experiments/{experiment_id}").json()
            assert server_payload["status"] == "running", server_payload
            assert server_payload["experiment_id"] == experiment_id
            assert server_payload["job_id"] == job_id
            expect(detail.locator(".sensitivity-status")).to_be_visible(timeout=10000)
            cancel_btn = detail.get_by_role("button", name="Hủy thử nghiệm", exact=True)
            create_btn = detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)
            expect(cancel_btn).to_be_visible()
            expect(create_btn).to_be_disabled()
            assert cancel_urls == []

            # Deliver the already fetched failed body, never continue/refetch this route.
            with page.expect_response(lambda r: r.request == stale_request) as delivered_response:
                stale_route.fulfill(response=snapshot)
            delivered = delivered_response.value
            assert delivered.status == 200
            assert delivered.finished() is None, "Old request must finish in the browser, not abort"
            delivered_payload = delivered.json()
            assert delivered_payload["status"] == "failed", "Browser must receive the captured failed attempt"
            assert delivered_payload == captured_payload
            assert delivered_payload["experiment_id"] == experiment_id
            assert delivered_payload["job_id"] == job_id
            print("C1 stale response: " + json.dumps({
                "experiment_id": experiment_id, "job_id": job_id,
                "captured": captured_payload["status"],
                "server_at_delivery": server_payload["status"],
                "delivered": delivered_payload["status"], "browser_finished": True,
            }))
            settle_browser(page)
            expect(detail.locator(".sensitivity-status")).to_be_visible()
            expect(cancel_btn).to_be_visible()
            expect(create_btn).to_be_disabled()
            assert cancel_urls == []
            assert client.get(f"/jobs/{job_id}").json()["status"] == "running"

            gate_lock.unlink(missing_ok=True)
            expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=15000)
            expect(create_btn).to_be_enabled()
            assert cancel_urls == []
            assert len(retry_requests) == 1
            assert client.get(f"/jobs/{job_id}").json()["status"] == "completed"
            page.unroute("**" + retry_path, hold_retry)
            page.unroute("**" + experiment_path, hold_stale_exp_get)
            _assert_expected_console_only(page_errors, console_errors)
        finally:
            gate_lock.unlink(missing_ok=True)
            entered_flag.unlink(missing_ok=True)
            fail_flag.unlink(missing_ok=True)
            for _, response, _ in held_snapshots:
                response.dispose()



def test_r3_e_retry_rejected_by_model_revision_404_network_keeps_review_draft(
    browser, gated_server
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R3-E Retry Rejections",
            "profile": "neu",
            "items": [
                {"text": M3_PAIR_INVALID_TEXT},
                {"text": M3_SWITCH_TEXT},
            ],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])
    items = client.get(f"/datasets/{ds['id']}/items").json()["items"]
    pair_item = next(i for i in items if i["text"] == M3_PAIR_INVALID_TEXT)

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    retry_requests = []
    page.on(
        "request",
        lambda req: retry_requests.append(req.url)
        if req.method == "POST" and req.url.endswith("/retry")
        else None,
    )

    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_role("button", name=M3_PAIR_INVALID_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")

    # Enter unsaved review draft that must remain untouched through all retry errors.
    draft_note = "Nháp rà soát giữ nguyên qua lỗi retry"
    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("0")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(draft_note)

    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "kết thúc"
    )
    run_btn = detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)
    run_btn.click()
    retry_btn = detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True)
    expect(retry_btn).to_be_visible(timeout=15000)

    err_alert = detail.locator(".sensitivity-body > p.error-text[role='alert']")
    model_flag = gated_server.runtime / "model_identity_v2.flag"

    # 1. Network abort on retry -> shows network error, no auto-retry loop, keeps draft.
    def abort_retry(route):
        route.abort()

    page.route("**/api/v1/jobs/*/retry", abort_retry)
    retry_btn.click()
    expect(err_alert).to_be_visible()
    expect(err_alert).to_have_text(
        "Không thể kết nối dịch vụ local. Kiểm tra API đang chạy rồi thử lại."
    )
    page.wait_for_timeout(500)
    assert len(retry_requests) == 1
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(
        draft_note
    )
    page.unroute("**/api/v1/jobs/*/retry", abort_retry)

    # 2. Real backend 409 MODEL_IDENTITY_CHANGED -> clear message, no auto-retry, keeps draft.
    model_flag.write_text("v2", encoding="utf-8")
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/retry")
    ) as model_409:
        retry_btn.click()
    assert model_409.value.status == 409
    assert model_409.value.json()["code"] == "MODEL_IDENTITY_CHANGED"
    expect(err_alert).to_contain_text(
        "Không thể chạy tiếp thử nghiệm cũ vì model, phiên bản văn bản hoặc trạng thái job đã thay đổi"
    )
    page.wait_for_timeout(400)
    assert len(retry_requests) == 2
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(
        draft_note
    )
    model_flag.unlink(missing_ok=True)

    # 3. Real backend 409 REVISION_CONFLICT -> clear message, keeps draft.
    assert (
        client.patch(
            f"/items/{pair_item['id']}/text",
            json={"text": "M3 pair invalid đã sửa bản 2.", "expected_revision": 1},
        ).status_code
        == 200
    )
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/retry")
    ) as rev_409:
        retry_btn.click()
    assert rev_409.value.status == 409
    assert rev_409.value.json()["code"] == "REVISION_CONFLICT"
    expect(err_alert).to_contain_text(
        "Không thể chạy tiếp thử nghiệm cũ vì model, phiên bản văn bản hoặc trạng thái job đã thay đổi"
    )
    assert len(retry_requests) == 3
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(
        draft_note
    )

    # 4. Real backend 404 NOT_FOUND (expired temp dataset) -> clear message, does not attach job.
    conn = sqlite3.connect(gated_server.runtime / "workspace.sqlite3", timeout=10.0)
    try:
        conn.execute("UPDATE datasets SET expires_at = 1.0 WHERE temporary = 1")
        conn.commit()
    finally:
        conn.close()

    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/retry")
    ) as not_found_404:
        retry_btn.click()
    assert not_found_404.value.status == 404
    expect(err_alert).to_contain_text(
        "Không thể chạy tiếp thử nghiệm cũ vì model, phiên bản văn bản hoặc trạng thái job đã thay đổi"
    )
    assert len(retry_requests) == 4
    expect(detail.locator(".sensitivity-status")).to_have_count(0)
    expect(run_btn).to_be_enabled()
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(
        draft_note
    )

    _assert_expected_console_only(
        page_errors,
        console_errors,
        ("net::ERR_FAILED", "status of 409", "status of 404"),
    )
    context.close()
    client.close()


# ---------------------------------------------------------------------------
# Responsive layout, keyboard focus, & screenshots for F4 verification
# ---------------------------------------------------------------------------


def test_r1_r2_responsive_keyboard_and_screenshots(
    browser, gated_server, screenshot_dir
):
    client = httpx.Client(base_url=gated_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "R1/R2 Responsive & Keyboard",
            "profile": "neu",
            "items": [
                {"text": M3_SWITCH_TEXT},
                {"text": M3_BLOCKER_TEXT},
            ],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])
    items = client.get(f"/datasets/{ds['id']}/items").json()["items"]
    switch_item = next(i for i in items if i["text"] == M3_SWITCH_TEXT)
    blocker_item = next(i for i in items if i["text"] == M3_BLOCKER_TEXT)

    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(gated_server.url + f"/#/datasets/{ds['id']}")

    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")

    # 1. Cross-revision conflict UI at desktop & mobile + keyboard navigation to Apply button.
    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("confirmed")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Nháp kiểm tra layout và bàn phím"
    )
    assert (
        client.patch(
            f"/items/{switch_item['id']}/text",
            json={"text": M3_REV2_TEXT, "expected_revision": 1},
        ).status_code
        == 200
    )
    _reconnect_and_refetch_item(page, switch_item["id"])

    conflict = detail.get_by_test_id("review-conflict-sentiment")
    expect(conflict).to_be_visible()
    conflict.scroll_into_view_if_needed()
    assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert_no_horizontal_overflow(page, "1440x960 r1 conflict")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "r1-desktop-conflict.png"), full_page=False)

    page.set_viewport_size({"width": 390, "height": 844})
    conflict.scroll_into_view_if_needed()
    assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert_no_horizontal_overflow(page, "390x844 r1 conflict")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "r1-mobile-conflict.png"), full_page=False)

    page.set_viewport_size({"width": 1440, "height": 960})
    apply_btn = detail.get_by_role(
        "button", name="Áp nháp lên văn bản hiện tại: cảm xúc", exact=True
    )
    apply_btn.focus()
    expect(apply_btn).to_be_focused()
    page.keyboard.press("Enter")
    expect(conflict).to_have_count(0)
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("corrected")
    save_sent_btn = detail.get_by_role("button", name="Lưu cảm xúc", exact=True)
    expect(save_sent_btn).to_be_enabled()
    save_sent_btn.scroll_into_view_if_needed()
    assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert_no_horizontal_overflow(page, "1440x960 r1 after apply")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "r1-desktop-after-apply.png"), full_page=False)

    # 2. Poll error + cancel button still usable at desktop & mobile.
    gate_lock = gated_server.runtime / "pair_gate.lock"
    entered_flag = gated_server.runtime / "pair_entered.flag"
    entered_flag.unlink(missing_ok=True)
    gate_lock.write_text("lock", encoding="utf-8")
    blocker_exp = _create_sensitivity_job_api(client, blocker_item, "kiểm tra")
    _wait_flag(entered_flag)

    def fail_poll_500(route):
        if route.request.method == "GET":
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"code": "POLL_500", "message": "Lỗi 500 giả lập kiểm tra giao diện."}),
            )
        else:
            route.continue_()

    page.route("**/api/v1/sensitivity-experiments/*", fail_poll_500)
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill("dự đoán")
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(
        detail.get_by_text("Lỗi 500 giả lập kiểm tra giao diện.", exact=True)
    ).to_be_visible(timeout=15000)
    expect(detail.locator(".sensitivity-status")).to_contain_text(
        "Không đọc được trạng thái thử nghiệm hiện tại"
    )
    cancel_btn = detail.get_by_role("button", name="Hủy thử nghiệm", exact=True)
    expect(cancel_btn).to_be_enabled()

    detail.locator(".sensitivity-result-area").scroll_into_view_if_needed()
    assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert_no_horizontal_overflow(page, "1440x960 r2 poll error")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "r2-desktop-poll-error.png"), full_page=False)

    page.set_viewport_size({"width": 390, "height": 844})
    detail.locator(".sensitivity-result-area").scroll_into_view_if_needed()
    assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert_no_horizontal_overflow(page, "390x844 r2 poll error")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "r2-mobile-poll-error.png"), full_page=False)

    cancel_btn.focus()
    expect(cancel_btn).to_be_focused()
    page.keyboard.press("Enter")
    expect(detail.get_by_text("Đã hủy thử nghiệm", exact=True)).to_be_visible(timeout=10000)

    gate_lock.unlink(missing_ok=True)
    _wait_job_terminal(client, blocker_exp["job_id"])
    page.unroute("**/api/v1/sensitivity-experiments/*", fail_poll_500)

    _assert_expected_console_only(page_errors, console_errors, ("status of 500",))
    context.close()
    client.close()


def _serve_gated():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve-gated", action="store_true")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    os.environ["FEEDBACK_RUNTIME"] = args.runtime
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from services.api.main import create_app
    import uvicorn

    app = create_app(
        args.runtime,
        registry=GatedControlledRegistry(args.runtime),
        start_worker=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="error")


if __name__ == "__main__":
    _serve_gated()
