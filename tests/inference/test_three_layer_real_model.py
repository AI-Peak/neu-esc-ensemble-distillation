"""Opt-in G3 real-model acceptance test for the three-layer NEU-ESC demo stack.

Copies the currently active production NEU bundle immutably into a temporary
runtime root (without re-importing or mutating source runtime/models), verifies
bundle hashes, runs offline CPU inference via separate API + Worker processes
and Playwright Chromium across:
- G3.1 Immutable active bundle copy, offline HF environment, no fake fallback
- G3.2 24-row `data/demo/three_layer_feedback_vi.csv` real inference & schema/score bounds
- G3.3 Dynamic Topic Attention verification, click-through, AI/effective + real review
- G3.4 Sensitivity experiment identity, exact variant, same-label deltas, source immutability
- G3.5 >128-token Vietnamese/emoji truncation & same-input `predict_pair` / `predict` parity
- G3.6 Cancel, API+Worker restart persistence (TTL experiment + byte-identical UI CSV export), source stale
- G3.7 Desktop & Mobile 390px screenshots, zero overflow, zero page/console errors, diagnostic JSON

NOTE: Must NEVER be collected/executed by default suite (`@pytest.mark.real_model`).
"""
from __future__ import annotations

import csv
import hashlib
import inspect
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import time

import httpx
import pytest

from services.inference.registry import ModelRegistry, sha256


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _terminate_proc(proc) -> None:
    if proc is not None and proc.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _start_stack(repo_root: Path, runtime_dir: Path, env: dict[str, str], log_dir: Path, label: str):
    log_dir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    worker_log_path = log_dir / f"worker-{label}.log"
    api_log_path = log_dir / f"api-{label}.log"
    worker_log = worker_log_path.open("w", encoding="utf-8")
    api_log = api_log_path.open("w", encoding="utf-8")
    worker_proc = subprocess.Popen(
        [sys.executable, "-m", "services.worker", "--runtime-dir", str(runtime_dir)],
        cwd=repo_root,
        env=env,
        stdout=worker_log,
        stderr=subprocess.STDOUT,
    )
    api_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "services.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=repo_root,
        env=env,
        stdout=api_log,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(150):
            if worker_proc.poll() is not None:
                worker_log.flush()
                tail = worker_log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
                raise RuntimeError(f"Real worker ({label}) exited early ({worker_proc.returncode}):\n{tail}")
            if api_proc.poll() is not None:
                api_log.flush()
                tail = api_log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
                raise RuntimeError(f"Real API ({label}) exited early ({api_proc.returncode}):\n{tail}")
            try:
                health = httpx.get(f"{base_url}/api/v1/health", timeout=1.0)
                if health.is_success and health.json().get("worker", {}).get("alive"):
                    return base_url, api_proc, worker_proc, api_log, worker_log
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise TimeoutError(f"Real API/worker ({label}) did not become healthy")
    except Exception:
        _stop_stack(api_proc, worker_proc, api_log, worker_log)
        raise


def _stop_stack(api_proc, worker_proc, api_log, worker_log) -> None:
    for proc in (api_proc, worker_proc):
        _terminate_proc(proc)
    for handle in (api_log, worker_log):
        if handle is not None and not handle.closed:
            handle.close()


def _verify_and_copy_active_bundle(template_models_root: Path, runtime_models_root: Path) -> dict:
    """Validate template active NEU bundle SHA-256 inventory and copy immutably."""
    pointer_src = template_models_root / "neu" / "current.json"
    if not pointer_src.is_file():
        pytest.skip(f"Active NEU pointer not found at {pointer_src}")

    pointer_data = json.loads(pointer_src.read_text(encoding="utf-8"))
    active_version = pointer_data.get("version")
    if not isinstance(active_version, str) or not active_version:
        pytest.skip(f"Invalid active version in {pointer_src}")

    src_version_dir = template_models_root / "neu" / "versions" / active_version
    src_manifest_path = src_version_dir / "manifest.json"
    if not src_version_dir.is_dir() or not src_manifest_path.is_file():
        pytest.skip(f"Active NEU bundle directory/manifest missing at {src_version_dir}")

    manifest = json.loads(src_manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("model_version") == active_version
    files_map = manifest.get("files") or {}
    for required_rel in (
        "model.safetensors",
        "encoder/config.json",
        "preprocessing.json",
        "tokenizer/tokenizer_config.json",
    ):
        assert required_rel in files_map, f"Missing {required_rel!r} in manifest files inventory"
    assert any(rel.startswith("tokenizer/") for rel in files_map)

    for rel_path, expected_hash in files_map.items():
        src_file = (src_version_dir / rel_path).resolve()
        assert src_file.is_relative_to(src_version_dir.resolve())
        assert src_file.is_file(), f"Missing source bundle file: {src_file}"
        assert sha256(src_file) == expected_hash, f"Source bundle SHA-256 mismatch for {rel_path}"

    src_manifest_sha256 = sha256(src_manifest_path)

    dst_neu = runtime_models_root / "neu"
    dst_versions = dst_neu / "versions"
    dst_versions.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pointer_src, dst_neu / "current.json")
    dst_version_dir = dst_versions / active_version
    shutil.copytree(src_version_dir, dst_version_dir)

    assert (dst_neu / "current.json").read_bytes() == pointer_src.read_bytes()
    for rel_path, expected_hash in files_map.items():
        dst_file = (dst_version_dir / rel_path).resolve()
        assert dst_file.is_file(), f"Missing copied bundle file: {dst_file}"
        assert not dst_file.is_symlink()
        assert sha256(dst_file) == expected_hash, f"Copied bundle SHA-256 mismatch for {rel_path}"

    dst_manifest_sha256 = sha256(dst_version_dir / "manifest.json")
    assert dst_manifest_sha256 == src_manifest_sha256

    preprocessing_sha256 = hashlib.sha256(
        json.dumps(
            manifest["preprocessing"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "active_version": active_version,
        "manifest": manifest,
        "manifest_sha256": dst_manifest_sha256,
        "preprocessing_sha256": preprocessing_sha256,
        "checkpoint_sha256": files_map["model.safetensors"],
    }


def _compute_expected_attention(items: list[dict], profile: dict, label_source: str) -> dict:
    """Independently compute attention structure from API items to cross-check /summary."""
    neg_id = next(e["id"] for e in profile["sentiment"] if e["key"].casefold() == "negative")
    toxic_ids = [e["id"] for e in profile["sentiment"] if e["key"].casefold() == "toxic"]
    toxic_id = toxic_ids[0] if toxic_ids else None
    valid_sent_ids = {e["id"] for e in profile["sentiment"]}
    valid_topic_ids = {e["id"] for e in profile["topic"]}
    threshold = 5

    filtered_count = 0
    eligible_count = 0
    missing_topic = 0
    missing_sent_with_topic = 0
    t_total: dict[int, int] = {}
    t_elig: dict[int, int] = {}
    t_neg: dict[int, int] = {}
    t_tox: dict[int, int] = {}

    for row in items:
        filtered_count += 1
        if label_source == "effective":
            s_val = row["effective"]["sentiment"]
            t_val = row["effective"]["topic"]
        else:
            pred = row.get("prediction") or {}
            s_val = (pred.get("sentiment") or {}).get("label_id")
            t_val = (pred.get("topic") or {}).get("label_id")

        t_ok = type(t_val) is int and t_val in valid_topic_ids
        s_ok = type(s_val) is int and s_val in valid_sent_ids
        if not t_ok:
            missing_topic += 1
            continue
        t_total[t_val] = t_total.get(t_val, 0) + 1
        if not s_ok:
            missing_sent_with_topic += 1
            continue
        eligible_count += 1
        t_elig[t_val] = t_elig.get(t_val, 0) + 1
        if s_val == neg_id:
            t_neg[t_val] = t_neg.get(t_val, 0) + 1
        elif toxic_id is not None and s_val == toxic_id:
            t_tox[t_val] = t_tox.get(t_val, 0) + 1

    topics = []
    for tid, count in t_total.items():
        elig = t_elig.get(tid, 0)
        neg = t_neg.get(tid, 0)
        tox = None if toxic_id is None else t_tox.get(tid, 0)
        topics.append(
            {
                "topic_id": tid,
                "topic_count": count,
                "eligible_count": elig,
                "negative_count": neg,
                "toxic_count": tox,
                "negative_rate": (neg / elig) if elig > 0 else None,
                "missing_sentiment_count": count - elig,
                "small_sample": elig < threshold,
            }
        )
    topics.sort(key=lambda r: (-r["negative_count"], -r["eligible_count"], r["topic_id"]))
    return {
        "ranking_rule": "negative_count_desc,eligible_count_desc,topic_id_asc",
        "small_sample_threshold": threshold,
        "negative_label_id": neg_id,
        "toxic_label_id": toxic_id,
        "filtered_count": filtered_count,
        "eligible_count": eligible_count,
        "missing_topic_count": missing_topic,
        "missing_sentiment_with_topic_count": missing_sent_with_topic,
        "topics": topics,
    }


def _utf16_span(full_text: str, needle: str, occurrence: int = 0) -> tuple[int, int]:
    search_from = 0
    found = -1
    for _ in range(occurrence + 1):
        found = full_text.find(needle, search_from)
        assert found != -1, f"Substring {needle!r} occurrence {occurrence} not found"
        search_from = found + 1
    start_utf16 = len(full_text[:found].encode("utf-16-le")) // 2
    end_utf16 = len(full_text[: found + len(needle)].encode("utf-16-le")) // 2
    return start_utf16, end_utf16


def _select_raw_text_utf16(detail_dialog, start_utf16: int, end_utf16: int) -> None:
    detail_dialog.locator("p.sensitivity-raw-text").evaluate(
        """(el, coords) => {
            const textNode = el.firstChild;
            if (!textNode || textNode.nodeType !== Node.TEXT_NODE) {
                throw new Error("Expected direct single text node inside .sensitivity-raw-text");
            }
            const range = document.createRange();
            range.setStart(textNode, coords.start);
            range.setEnd(textNode, coords.end);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
        }""",
        {"start": start_utf16, "end": end_utf16},
    )


def _track_errors(page):
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda err: page_errors.append(str(err)))
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    return page_errors, console_errors


def _assert_no_horizontal_overflow(page, label: str = "") -> None:
    ok = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert ok, f"Horizontal overflow detected ({label}): " + str(
        page.evaluate("({scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth})")
    )


def _prepare_screenshot(page) -> None:
    try:
        toast_close = page.locator(".toast button").first
        if toast_close.is_visible():
            toast_close.click(timeout=500)
    except Exception:
        pass
    page.evaluate("window.scrollTo(0, 0)")


def _save_m4_screenshot(page, tmp_path: Path, filename: str) -> Path:
    target = tmp_path / filename
    page.screenshot(path=str(target), full_page=False)
    extra_dir = os.environ.get("QA_M4_SCREENSHOT_DIR")
    if extra_dir:
        extra_path = Path(extra_dir)
        extra_path.mkdir(parents=True, exist_ok=True)
        mirror = extra_path / filename
        mirror.write_bytes(target.read_bytes())
        return mirror
    return target


def _assert_score_distribution(pred: dict, active_version: str) -> None:
    assert pred is not None
    assert pred["model_id"] == "neu-phobert-mtl-ed-s42"
    assert pred["model_version"] == active_version
    assert pred["schema_id"] == "neu-v1"
    for task, expected_len in (("sentiment", 4), ("topic", 10)):
        scores = pred[task]["scores"]
        assert isinstance(scores, list) and len(scores) == expected_len
        assert all(isinstance(v, (int, float)) and math.isfinite(v) and 0.0 <= v <= 1.0 for v in scores)
        assert sum(scores) == pytest.approx(1.0, abs=1e-4)
        assert pred[task]["label_id"] == max(range(expected_len), key=scores.__getitem__)


def _assert_truncation_warning_consistency(result_obj: dict, results_locator) -> None:
    from playwright.sync_api import expect

    assert type(result_obj["model_input_equal"]) is bool
    warnings = result_obj["warnings"]
    assert "SENSITIVITY_NOT_CAUSAL" in warnings
    assert result_obj["baseline"]["prediction"]["truncated"] is True
    assert "INPUT_TRUNCATED_BASELINE" in warnings
    if result_obj["model_input_equal"] is True:
        assert "MODEL_INPUT_UNCHANGED" in warnings
        assert "TOKEN_WINDOW_MAY_CHANGE" not in warnings
        expect(results_locator).to_contain_text(
            "Sau tiền xử lý và cắt ngắn, đầu vào model của hai văn bản giống nhau."
        )
    else:
        assert "TOKEN_WINDOW_MAY_CHANGE" in warnings
        assert "MODEL_INPUT_UNCHANGED" not in warnings
        expect(results_locator).to_contain_text(
            "Bỏ đoạn có thể đổi cách tách từ và đưa phần văn bản phía sau vào giới hạn 128 token."
        )


@pytest.mark.real_model
def test_real_model_three_layer_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Opt-in G3 end-to-end acceptance on immutable active NEU PhoBERT checkpoint."""
    repo_root = Path(__file__).resolve().parents[2]
    template_models_root = Path(
        os.environ.get("FEEDBACK_REAL_BUNDLE_TEMPLATE", repo_root / "runtime" / "models")
    ).resolve()
    dist_index = repo_root / "apps" / "web" / "dist" / "index.html"
    demo_csv = repo_root / "data" / "demo" / "three_layer_feedback_vi.csv"

    if not dist_index.is_file():
        pytest.skip(f"Frontend build not found at {dist_index}")
    if not demo_csv.is_file():
        pytest.skip(f"Demo CSV not found at {demo_csv}")

    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    safetensors = pytest.importorskip("safetensors")
    underthesea = pytest.importorskip("underthesea")
    from playwright.sync_api import expect, sync_playwright

    # G3.1: Verify ModelRegistry production source has no fake/mock fallback.
    registry_src = inspect.getsource(ModelRegistry)
    assert "Controlled" not in registry_src
    assert "mock" not in registry_src.lower()
    assert "fake" not in registry_src.lower()

    runtime_dir = tmp_path / "real-model-runtime"
    bundle_info = _verify_and_copy_active_bundle(template_models_root, runtime_dir / "models")
    active_version = bundle_info["active_version"]

    empty_hf = tmp_path / "empty-hf-cache"
    (empty_hf / "hub").mkdir(parents=True, exist_ok=True)
    log_dir = tmp_path / "logs"

    env = os.environ.copy()
    env["FEEDBACK_RUNTIME"] = str(runtime_dir)
    env["HF_HOME"] = str(empty_hf)
    env["HF_HUB_CACHE"] = str(empty_hf / "hub")
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["PYTHONUTF8"] = "1"

    api_proc = worker_proc = api_log = worker_log = None
    try:
        base_url, api_proc, worker_proc, api_log, worker_log = _start_stack(
            repo_root, runtime_dir, env, log_dir, "run1"
        )

        health1 = httpx.get(f"{base_url}/api/v1/health", timeout=5.0).json()
        assert health1["database_version"] == 2
        assert health1["worker"]["alive"] is True
        worker1_pid = health1["worker"]["pid"]

        profiles = httpx.get(f"{base_url}/api/v1/profiles", timeout=5.0).json()
        by_profile = {p["id"]: p for p in profiles}
        neu_profile = by_profile["neu"]
        assert neu_profile["model"]["available"] is True
        assert neu_profile["model"]["model_id"] == "neu-phobert-mtl-ed-s42"
        assert neu_profile["model"]["model_version"] == active_version
        assert neu_profile["model"]["schema_id"] == "neu-v1"
        assert by_profile["uit"]["model"]["available"] is False

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1440, "height": 960}, accept_downloads=True)
            page = ctx.new_page()
            page_errors, console_errors = _track_errors(page)

            # G3.2: Import 24-row demo CSV via UI & run real model analysis.
            page.goto(base_url)
            expect(page.get_by_test_id("create-dataset")).to_be_visible()
            page.get_by_test_id("create-dataset").click()
            page.get_by_test_id("dataset-name").fill("Demo Ba Tầng PhoBERT Thật")
            page.locator(".import-form label", has_text="Loại nội dung").locator("select").select_option("neu")
            page.get_by_test_id("file-upload").set_input_files(str(demo_csv))
            expect(page.get_by_test_id("text-column")).to_have_value("text")
            page.get_by_test_id("import-confirm").click()
            expect(page.get_by_role("heading", name="Demo Ba Tầng PhoBERT Thật", exact=True)).to_be_visible()
            dataset_id = page.url.split("/datasets/")[-1]

            page.get_by_test_id("analyze").click()
            expect(page.get_by_text("24/24 kết quả đã lưu", exact=True)).to_be_visible(timeout=180000)

            with httpx.Client(base_url=f"{base_url}/api/v1", timeout=15.0) as client:
                items_page = client.get(f"/datasets/{dataset_id}/items", params={"page_size": 25}).json()
                assert items_page["total"] == 24
                items_initial = items_page["items"]
                assert len(items_initial) == 24

                flagged_sentiment = 0
                flagged_topic = 0
                truncated_count = 0
                pending_signal_count = 0
                for it in items_initial:
                    _assert_score_distribution(it["prediction"], active_version)
                    sig = it["review_signals"]
                    assert sig is not None
                    assert sig["policy_id"] == "review-signals-v1"
                    assert sig["experimental"] is True
                    assert sig["sentiment"]["state"] in ("flagged", "clear")
                    assert sig["topic"]["state"] in ("flagged", "clear")
                    if sig["sentiment"]["state"] == "flagged":
                        flagged_sentiment += 1
                    if sig["topic"]["state"] == "flagged":
                        flagged_topic += 1
                    if sig["truncated"] is True:
                        truncated_count += 1
                    if sig["pending_signal_review"] is True:
                        pending_signal_count += 1

                # G3.3: Compute expected attention directly from response rows & verify AI vs effective.
                summary_eff_before = client.get(
                    f"/datasets/{dataset_id}/summary", params={"label_source": "effective"}
                ).json()
                summary_ai_before = client.get(
                    f"/datasets/{dataset_id}/summary", params={"label_source": "ai"}
                ).json()
                assert summary_eff_before["attention"] == _compute_expected_attention(
                    items_initial, neu_profile, "effective"
                )
                assert summary_ai_before["attention"] == _compute_expected_attention(
                    items_initial, neu_profile, "ai"
                )
                assert summary_eff_before["attention"] == summary_ai_before["attention"]

                expect(page.locator(".attention-table tbody tr").first).to_be_visible()
                top_topic = summary_eff_before["attention"]["topics"][0]
                if top_topic["negative_count"] > 0:
                    top_topic_name = next(
                        entry["name"] for entry in neu_profile["topic"] if entry["id"] == top_topic["topic_id"]
                    )
                    neg_id = summary_eff_before["attention"]["negative_label_id"]
                    expected_neg_ids = [
                        it["id"]
                        for it in sorted(items_initial, key=lambda x: x["source_row"])
                        if it["effective"]["topic"] == top_topic["topic_id"]
                        and it["effective"]["sentiment"] == neg_id
                    ]
                    page.get_by_role(
                        "button",
                        name=f"Xem {top_topic['negative_count']} phản hồi tiêu cực của chủ đề {top_topic_name}",
                        exact=True,
                    ).click()
                    expect(page.get_by_role("tab", name="Tất cả phản hồi", exact=True)).to_have_attribute(
                        "aria-selected", "true"
                    )
                    filtered_items = client.get(
                        f"/datasets/{dataset_id}/items",
                        params={
                            "topic": top_topic["topic_id"],
                            "sentiment": neg_id,
                            "sort": "source_row",
                            "direction": "asc",
                            "page_size": 25,
                        },
                    ).json()["items"]
                    assert [it["id"] for it in filtered_items] == expected_neg_ids
                    expect(page.locator(".item-table tbody tr")).to_have_count(len(expected_neg_ids))
                    for row_idx, exp_item in enumerate(filtered_items):
                        expect(page.locator(".item-table tbody tr").nth(row_idx)).to_contain_text(
                            exp_item["text"]
                        )
                    page.get_by_role("button", name=re.compile(r"^Bỏ lọc")).click()
                    page.get_by_role("tab", name="Tổng quan", exact=True).click()

                # Real UI human review on row 1 changing sentiment across Negative boundary so attention updates.
                review_item = sorted(items_initial, key=lambda x: x["source_row"])[0]
                orig_sent_id = review_item["prediction"]["sentiment"]["label_id"]
                neg_label_id = summary_eff_before["attention"]["negative_label_id"]
                target_sent_id = neg_label_id if orig_sent_id != neg_label_id else (neg_label_id + 1) % 4
                review_note = "Rà soát thật thay đổi cảm xúc để kiểm chứng tách AI vs Effective"

                page.locator(".item-table tbody tr", has_text=review_item["text"]).locator("button").first.click()
                detail = page.locator("dialog.detail-panel")
                expect(detail).to_be_visible()
                detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
                detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option(str(target_sent_id))
                detail.get_by_label("Ghi chú cảm xúc", exact=True).fill(review_note)
                detail.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
                expect(detail.get_by_text("Đã lưu · bản duyệt 1", exact=True)).to_be_visible()
                detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

                reviewed_item_api = client.get(f"/items/{review_item['id']}").json()
                assert reviewed_item_api["prediction"] == review_item["prediction"]
                assert reviewed_item_api["reviews"]["sentiment"]["status"] == "corrected"
                assert reviewed_item_api["reviews"]["sentiment"]["label_id"] == target_sent_id
                assert reviewed_item_api["reviews"]["sentiment"]["note"] == review_note
                assert reviewed_item_api["reviews"]["topic"] is None
                assert (
                    reviewed_item_api["review_signals"]["sentiment"]["reasons"]
                    == review_item["review_signals"]["sentiment"]["reasons"]
                )

                items_after_review = client.get(
                    f"/datasets/{dataset_id}/items", params={"page_size": 25}
                ).json()["items"]
                summary_eff_after = client.get(
                    f"/datasets/{dataset_id}/summary", params={"label_source": "effective"}
                ).json()
                summary_ai_after = client.get(
                    f"/datasets/{dataset_id}/summary", params={"label_source": "ai"}
                ).json()
                assert summary_ai_after["attention"] == summary_ai_before["attention"]
                assert summary_eff_after["attention"] == _compute_expected_attention(
                    items_after_review, neu_profile, "effective"
                )
                assert summary_eff_after["attention"] != summary_ai_after["attention"]

                source_select = page.locator(".source-controls label").first.locator("select")
                source_select.select_option("ai")
                expect(page.locator(".attention-header")).to_contain_text("Chỉ dự đoán AI gốc")
                source_select.select_option("effective")
                expect(page.locator(".attention-header")).to_contain_text("Đã duyệt nếu có, còn lại AI")

                # G3.6 (Export before sensitivity, restart, edit & append): create canonical UI CSV export.
                page.get_by_test_id("export").click()
                export_dialog = page.get_by_role("dialog", name="Xuất kết quả CSV", exact=True)
                export_dialog.locator("select").select_option("all")
                with page.expect_response(
                    lambda r: r.request.method == "POST"
                    and r.url == f"{base_url}/api/v1/datasets/{dataset_id}/exports"
                ) as export_resp_info:
                    export_dialog.get_by_role("button", name="Tạo bản chụp CSV", exact=True).click()
                assert export_resp_info.value.status == 201
                export_meta = export_resp_info.value.json()
                export_id = export_meta["id"]
                export_path = export_meta["url"]
                assert export_path == f"/api/v1/exports/{export_id}"
                assert export_meta["row_count"] == 24

                dl_link = export_dialog.get_by_role("link", name="Tải CSV", exact=True)
                expect(dl_link).to_have_attribute("href", export_path)
                with page.expect_download() as dl_info:
                    dl_link.click()
                export_csv_path = tmp_path / "real-export-24.csv"
                dl_info.value.save_as(export_csv_path)
                export_bytes_before = export_csv_path.read_bytes()
                assert export_bytes_before.startswith(b"\xef\xbb\xbf")
                export_rows = list(csv.DictReader(io.StringIO(export_bytes_before.decode("utf-8-sig"))))
                assert len(export_rows) == 24
                assert all(r["model_version"] == active_version and r["schema_id"] == "neu-v1" for r in export_rows)
                row0 = next(r for r in export_rows if r["item_id"] == review_item["id"])
                assert row0["review_sentiment_status"] == "corrected"
                assert row0["effective_sentiment"] == str(target_sent_id)
                assert row0["review_topic_status"] == "unreviewed"
                export_dialog.get_by_role("button", name="Đóng", exact=True).last.click()

                # G3.4: Real Sensitivity Experiment on row 2 (verbatim phrase), desktop screenshot, source immutability.
                sens_item = sorted(items_after_review, key=lambda x: x["source_row"])[1]
                selection_phrase = "sát ngày"
                assert sens_item["text"].count(selection_phrase) == 1
                start_u16, end_u16 = _utf16_span(sens_item["text"], selection_phrase)
                expected_variant_text = sens_item["text"].replace(selection_phrase, "", 1)

                reviews_hist_before = client.get(f"/items/{sens_item['id']}/reviews").json()
                revisions_hist_before = client.get(f"/items/{sens_item['id']}/revisions").json()

                page.locator(".item-table tbody tr", has_text=sens_item["text"]).locator("button").first.click()
                expect(detail).to_be_visible()
                detail.locator("details.sensitivity-panel summary").click()
                _select_raw_text_utf16(detail, start_u16, end_u16)
                expect(
                    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True)
                ).to_have_value(selection_phrase)
                expect(detail.locator(".sensitivity-variant-preview")).to_have_text(expected_variant_text)

                with page.expect_response(
                    lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
                ) as exp_post:
                    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
                assert exp_post.value.status == 202
                exp_id = exp_post.value.json()["experiment_id"]

                results_box = detail.locator(".sensitivity-results")
                expect(results_box).to_be_visible(timeout=60000)
                expect(results_box).to_contain_text(
                    "Thử nghiệm độ nhạy: thay đổi đầu vào có thể làm thay đổi nghĩa; đây không phải bằng chứng chắc chắn về nguyên nhân model dự đoán."
                )
                assert detail.get_by_role("button", name=re.compile(r"Áp dụng biến thể", re.I)).count() == 0

                results_box.get_by_role("button", name="Xem tất cả 4 nhãn", exact=True).click()
                results_box.get_by_role("button", name="Xem tất cả 10 nhãn", exact=True).click()

                exp_detail = client.get(f"/sensitivity-experiments/{exp_id}").json()
                assert exp_detail["status"] == "completed"
                assert exp_detail["execution"]["profile"] == "neu"
                assert exp_detail["execution"]["schema_id"] == "neu-v1"
                assert exp_detail["execution"]["model_id"] == "neu-phobert-mtl-ed-s42"
                assert exp_detail["execution"]["model_version"] == active_version
                assert exp_detail["execution"]["manifest_sha256"] == bundle_info["manifest_sha256"]
                assert exp_detail["execution"]["preprocessing_sha256"] == bundle_info["preprocessing_sha256"]
                assert exp_detail["execution"]["mode"] == "cpu-fp32-eval"
                assert exp_detail["execution"]["baseline_recomputed"] is True

                exp_res = exp_detail["result"]
                assert exp_res is not None
                assert exp_res["baseline"]["text"] == sens_item["text"]
                assert exp_res["variant"]["text"] == expected_variant_text
                assert "SENSITIVITY_NOT_CAUSAL" in exp_res["warnings"]
                _assert_score_distribution(exp_res["baseline"]["prediction"], active_version)
                _assert_score_distribution(exp_res["variant"]["prediction"], active_version)

                task_blocks = results_box.locator(".sensitivity-task-block")
                for block_idx, (task, label_count) in enumerate((("sentiment", 4), ("topic", 10))):
                    comp = exp_res["comparison"][task]
                    b_scores = exp_res["baseline"]["prediction"][task]["scores"]
                    v_scores = exp_res["variant"]["prediction"][task]["scores"]
                    assert comp["baseline_label_id"] == exp_res["baseline"]["prediction"][task]["label_id"]
                    assert comp["variant_label_id"] == exp_res["variant"]["prediction"][task]["label_id"]
                    assert len(comp["scores"]) == label_count
                    tbody_rows = task_blocks.nth(block_idx).locator("tbody tr")
                    expect(tbody_rows).to_have_count(label_count)
                    for idx, score_row in enumerate(comp["scores"]):
                        assert score_row["label_id"] == idx
                        assert score_row["before"] == pytest.approx(b_scores[idx], abs=1e-9)
                        assert score_row["after"] == pytest.approx(v_scores[idx], abs=1e-9)
                        assert score_row["delta"] == pytest.approx(v_scores[idx] - b_scores[idx], abs=1e-9)
                        cells = tbody_rows.nth(idx).locator("td")
                        before_str = cells.nth(1).inner_text().strip()
                        after_str = cells.nth(2).inner_text().strip()
                        delta_str = cells.nth(3).inner_text().strip()
                        assert re.fullmatch(r"\d\.\d{3}", before_str)
                        assert re.fullmatch(r"\d\.\d{3}", after_str)
                        assert re.fullmatch(r"[+-]?\d+\.\d{3}", delta_str)
                        assert not delta_str.startswith("-0.000") and not delta_str.startswith("+0.000")
                        assert abs(float(before_str) - score_row["before"]) <= 0.00051
                        assert abs(float(after_str) - score_row["after"]) <= 0.00051
                        assert abs(float(delta_str) - score_row["delta"]) <= 0.00051

                results_box.scroll_into_view_if_needed()
                assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
                _assert_no_horizontal_overflow(page, "1440x960 real model sensitivity")
                _prepare_screenshot(page)
                desktop_shot_path = _save_m4_screenshot(page, tmp_path, "m4-desktop-real-model.png")
                detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

                # Verify source immutability after sensitivity experiment.
                sens_item_after = client.get(f"/items/{sens_item['id']}").json()
                assert sens_item_after["text"] == sens_item["text"]
                assert sens_item_after["prediction"] == sens_item["prediction"]
                assert sens_item_after["reviews"] == sens_item["reviews"]
                assert client.get(f"/items/{sens_item['id']}/reviews").json() == reviews_hist_before
                assert client.get(f"/items/{sens_item['id']}/revisions").json() == revisions_hist_before
                assert client.get(f"/datasets/{dataset_id}/summary").json() == summary_eff_after
                assert client.get(f"/exports/{export_id}").content == export_bytes_before
                assert len(client.get("/datasets").json()) == 1

                # G3.6 (Deterministic Cancel while worker stopped before restart).
                _terminate_proc(worker_proc)
                worker_proc = None
                cancel_item = sorted(items_after_review, key=lambda x: x["source_row"])[2]
                page.locator(".item-table tbody tr", has_text=cancel_item["text"]).locator("button").first.click()
                expect(detail).to_be_visible()
                detail.locator("details.sensitivity-panel summary").click()
                detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill("ba câu")
                with page.expect_response(
                    lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
                ) as cancel_post:
                    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
                cancel_exp_id = cancel_post.value.json()["experiment_id"]
                cancel_btn = detail.get_by_role("button", name="Hủy thử nghiệm", exact=True)
                expect(cancel_btn).to_be_visible()
                cancel_btn.click()
                expect(detail.get_by_text("Đã hủy thử nghiệm", exact=True)).to_be_visible()
                assert client.get(f"/sensitivity-experiments/{cancel_exp_id}").json()["status"] == "cancelled"
                detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

            # G3.6 (Restart API + Worker on same runtime_dir).
            _stop_stack(api_proc, worker_proc, api_log, worker_log)
            api_proc = worker_proc = api_log = worker_log = None
            base_url2, api_proc, worker_proc, api_log, worker_log = _start_stack(
                repo_root, runtime_dir, env, log_dir, "run2"
            )

            with httpx.Client(base_url=f"{base_url2}/api/v1", timeout=15.0) as client2:
                health2 = client2.get("/health").json()
                assert health2["worker"]["alive"] is True
                assert health2["worker"]["pid"] != worker1_pid

                # Exact UI-created export returns 200 with byte-identical payload on restarted origin.
                restarted_export = httpx.get(f"{base_url2}{export_path}", timeout=5.0)
                assert restarted_export.status_code == 200
                assert restarted_export.content == export_bytes_before

                # Completed sensitivity experiment still within 15m TTL returns 200 & matches execution/result.
                persisted_exp = client2.get(f"/sensitivity-experiments/{exp_id}").json()
                assert persisted_exp["status"] == "completed"
                assert persisted_exp["source_stale"] is False
                assert persisted_exp["active_model_changed"] is False
                assert persisted_exp["execution"] == exp_detail["execution"]
                assert persisted_exp["result"] == exp_detail["result"]

                # G3.7 Mobile 390x844 layout & screenshot on clean 24-row real-model dataset.
                mobile_ctx = browser.new_context(viewport={"width": 390, "height": 844})
                mpage = mobile_ctx.new_page()
                m_page_errors, m_console_errors = _track_errors(mpage)
                mpage.goto(f"{base_url2}/#/datasets/{dataset_id}")
                expect(mpage.get_by_role("heading", name="Demo Ba Tầng PhoBERT Thật", exact=True)).to_be_visible()
                expect(mpage.locator(".attention-table tbody tr").first).to_be_visible()
                expect(mpage.locator(".attention-table thead")).not_to_be_visible()
                _assert_no_horizontal_overflow(mpage, "390x844 real model overview")
                _prepare_screenshot(mpage)
                mobile_shot_path = _save_m4_screenshot(mpage, tmp_path, "m4-mobile-390-real-model.png")

                # Check mobile ItemDetail overflow too before closing mobile context.
                mpage.locator(".item-table tbody tr", has_text=sens_item["text"]).locator("button").first.click()
                m_detail = mpage.locator("dialog.detail-panel")
                expect(m_detail).to_be_visible()
                assert m_detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
                _assert_no_horizontal_overflow(mpage, "390x844 real model detail")
                assert not m_page_errors
                assert not m_console_errors
                mobile_ctx.close()

                # Navigate desktop page to restarted origin.
                page.goto(f"{base_url2}/#/datasets/{dataset_id}")
                expect(page.get_by_role("heading", name="Demo Ba Tầng PhoBERT Thật", exact=True)).to_be_visible()

                # G3.6 source revision edit -> persisted experiment transitions to source_stale=True.
                page.locator(".item-table tbody tr", has_text=sens_item["text"]).locator("button").first.click()
                expect(detail).to_be_visible()
                detail.get_by_role("button", name="Sửa văn bản", exact=True).click()
                detail.get_by_label("Sửa văn bản phản hồi", exact=True).fill(
                    sens_item["text"] + " Đã cập nhật phản ánh."
                )
                detail.get_by_role("button", name="Lưu phiên bản văn bản", exact=True).click()
                expect(detail.get_by_text("Phiên bản 2", exact=True)).to_be_visible()
                detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

                stale_exp = client2.get(f"/sensitivity-experiments/{exp_id}").json()
                assert stale_exp["source_stale"] is True
                assert stale_exp["baseline_text"] == sens_item["text"]
                assert stale_exp["result"] == exp_detail["result"]

                # G3.5 + G3.6 Append >128-token text with emoji + NFD diacritics -> analyze -> old export unchanged.
                head_phrase = "Góp ý đầu kỳ về Ca\u0301n bộ hỗ trợ 🎉: "
                tail_phrase = " phần ghi chú phụ ở cuối câu."
                middle_body = " ".join(["nội dung này cần xem xét kỹ hơn nữa"] * 24)
                long_text = head_phrase + middle_body + tail_phrase
                assert long_text.count(head_phrase) == 1
                assert long_text.count(tail_phrase) == 1
                assert len(long_text) <= 5000

                page.locator("details.append-section summary").click()
                page.get_by_label("Phản hồi mới (mỗi dòng một câu)", exact=True).fill(long_text)
                page.get_by_role("button", name="Thêm phản hồi", exact=True).click()
                expect(page.get_by_text("(25)", exact=False)).to_be_visible()

                page.get_by_test_id("analyze").click()
                expect(page.get_by_text("25/25 kết quả đã lưu", exact=True)).to_be_visible(timeout=180000)

                # Old 24-row export snapshot must stay byte-identical after source edit, append, and reanalysis.
                after_append_export = httpx.get(f"{base_url2}{export_path}", timeout=5.0)
                assert after_append_export.status_code == 200
                assert after_append_export.content == export_bytes_before

                items_25 = client2.get(
                    f"/datasets/{dataset_id}/items", params={"page_size": 25}
                ).json()["items"]
                long_item = next(it for it in items_25 if it["text"] == long_text)
                assert long_item["prediction"]["truncated"] is True
                assert long_item["prediction"]["token_count_before_truncation"] > 128

                page.locator(".item-table tbody tr", has_text="Góp ý đầu kỳ về").locator("button").first.click()
                expect(detail).to_be_visible()
                expect(
                    detail.get_by_text(
                        f"Model đã cắt ngắn đầu vào ({long_item['prediction']['token_count_before_truncation']} token trước cắt). Kết quả không phản ánh đầy đủ toàn văn.",
                        exact=True,
                    )
                ).to_be_visible()
                detail.locator("details.sensitivity-panel summary").click()

                # NFD grapheme guard: "Ca" cannot split "Ca\u0301n".
                long_q_input = detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True)
                long_q_input.fill("Ca")
                expect(
                    detail.get_by_text(
                        "Đoạn khớp cắt ngang ký tự tổ hợp hoặc emoji nên không được chọn.",
                        exact=True,
                    )
                ).to_be_visible()

                # G3.5 Case 1: Remove tail phrase (no forced equality assertion; verify consistency).
                tail_expected_variant = long_text.replace(tail_phrase, "", 1)
                long_q_input.fill(tail_phrase)
                expect(detail.locator(".sensitivity-variant-preview")).to_have_text(
                    tail_expected_variant
                )
                with page.expect_response(
                    lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
                ) as tail_post:
                    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
                tail_exp_id = tail_post.value.json()["experiment_id"]
                expect(
                    detail.locator(".sensitivity-results .sensitivity-pair-text").nth(1)
                ).to_have_text(tail_expected_variant, timeout=60000)
                expect(detail.locator(".sensitivity-results")).to_be_visible()
                tail_exp = client2.get(f"/sensitivity-experiments/{tail_exp_id}").json()
                assert tail_exp["status"] == "completed"
                _assert_truncation_warning_consistency(tail_exp["result"], detail.locator(".sensitivity-results"))

                # G3.5 Case 2: Remove head phrase containing NFD + emoji.
                head_expected_variant = long_text.replace(head_phrase, "", 1)
                long_q_input.fill(head_phrase)
                expect(detail.locator(".sensitivity-variant-preview")).to_have_text(
                    head_expected_variant
                )
                with page.expect_response(
                    lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
                ) as head_post:
                    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
                head_exp_id = head_post.value.json()["experiment_id"]
                expect(
                    detail.locator(".sensitivity-results .sensitivity-pair-text").nth(1)
                ).to_have_text(head_expected_variant, timeout=60000)
                expect(detail.locator(".sensitivity-results")).to_be_visible()
                head_exp = client2.get(f"/sensitivity-experiments/{head_exp_id}").json()
                assert head_exp["status"] == "completed"
                _assert_truncation_warning_consistency(head_exp["result"], detail.locator(".sensitivity-results"))

                detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

            assert not page_errors, f"Unexpected pageerror(s): {page_errors}"
            assert not console_errors, f"Unexpected console.error(s): {console_errors}"
            ctx.close()
            browser.close()

        # Stop API + Worker before loading PhoBERT directly in test process (single model in RAM).
        _stop_stack(api_proc, worker_proc, api_log, worker_log)
        api_proc = worker_proc = api_log = worker_log = None

        monkeypatch.setenv("FEEDBACK_RUNTIME", str(runtime_dir))
        monkeypatch.setenv("HF_HOME", str(empty_hf))
        monkeypatch.setenv("HF_HUB_CACHE", str(empty_hf / "hub"))
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

        registry = ModelRegistry(runtime_dir / "models")
        identity = registry.execution_identity("neu")
        assert identity["model_id"] == "neu-phobert-mtl-ed-s42"
        assert identity["model_version"] == active_version
        assert identity["manifest_sha256"] == bundle_info["manifest_sha256"]
        assert identity["preprocessing_sha256"] == bundle_info["preprocessing_sha256"]

        # G3.5 Same-input parity test on >128-token text through ModelRegistry.predict_pair & predict.
        same_items = [
            {"item_id": "same-a", "revision_id": "rev-a", "text": long_text},
            {"item_id": "same-b", "revision_id": "rev-b", "text": long_text},
        ]
        pair_same = registry.predict_pair("neu", same_items, identity)
        assert pair_same["execution_identity"] == identity
        assert pair_same["model_input_equal"] is True
        p_a, p_b = pair_same["predictions"]
        assert p_a["truncated"] is True and p_b["truncated"] is True
        assert p_a["token_count_before_truncation"] > 128
        assert p_a["token_count_before_truncation"] == p_b["token_count_before_truncation"]
        max_score_diff_pair = 0.0
        for task in ("sentiment", "topic"):
            assert p_a[task]["label_id"] == p_b[task]["label_id"]
            diff = max(abs(x - y) for x, y in zip(p_a[task]["scores"], p_b[task]["scores"]))
            max_score_diff_pair = max(max_score_diff_pair, diff)
            assert diff < 1e-6

        single_pred = registry.predict("neu", [same_items[0]])[0]
        assert single_pred["model_version"] == active_version
        assert single_pred["token_count_before_truncation"] == p_a["token_count_before_truncation"]
        max_score_diff_vs_predict = 0.0
        for task in ("sentiment", "topic"):
            assert single_pred[task]["label_id"] == p_a[task]["label_id"]
            diff = max(abs(x - y) for x, y in zip(single_pred[task]["scores"], p_a[task]["scores"]))
            max_score_diff_vs_predict = max(max_score_diff_vs_predict, diff)
            assert single_pred[task]["scores"] == pytest.approx(p_a[task]["scores"], abs=1e-5)

        unexpected_hf_files = [
            p.relative_to(empty_hf).as_posix()
            for p in empty_hf.rglob("*")
            if p.is_file() and p.relative_to(empty_hf).as_posix() != "hub/version.txt"
        ]
        assert unexpected_hf_files == []
        version_marker = empty_hf / "hub" / "version.txt"
        if version_marker.is_file():
            assert version_marker.read_text(encoding="utf-8").strip() == "1"

        diagnostic_payload = {
            "active_version": active_version,
            "model_id": "neu-phobert-mtl-ed-s42",
            "schema_id": "neu-v1",
            "manifest_sha256": bundle_info["manifest_sha256"],
            "preprocessing_sha256": bundle_info["preprocessing_sha256"],
            "checkpoint_sha256": bundle_info["checkpoint_sha256"],
            "dependency_versions": {
                "python": platform.python_version(),
                "torch": torch.__version__,
                "transformers": transformers.__version__,
                "safetensors": safetensors.__version__,
                "underthesea": underthesea.__version__,
            },
            "environment": {
                "platform": platform.platform(),
                "cpu_count": os.cpu_count(),
                "device": "cpu",
                "mode": "cpu-fp32-eval",
            },
            "attention_summary": {
                "effective_before_review": summary_eff_before["attention"],
                "ai_before_review": summary_ai_before["attention"],
                "effective_after_review": summary_eff_after["attention"],
            },
            "flagged_count": {
                "total_items": 24,
                "sentiment_flagged": flagged_sentiment,
                "topic_flagged": flagged_topic,
                "truncated": truncated_count,
                "pending_signal_review": pending_signal_count,
            },
            "reviewed_item": {
                "item_id": review_item["id"],
                "source_row": review_item["source_row"],
                "original_sentiment_id": orig_sent_id,
                "corrected_sentiment_id": target_sent_id,
            },
            "sensitivity_experiment_summary": {
                "experiment_id": exp_id,
                "item_id": sens_item["id"],
                "selection_text": selection_phrase,
                "baseline_sentiment_label_id": exp_res["comparison"]["sentiment"]["baseline_label_id"],
                "variant_sentiment_label_id": exp_res["comparison"]["sentiment"]["variant_label_id"],
                "baseline_topic_label_id": exp_res["comparison"]["topic"]["baseline_label_id"],
                "variant_topic_label_id": exp_res["comparison"]["topic"]["variant_label_id"],
                "model_input_equal": exp_res["model_input_equal"],
                "warnings": exp_res["warnings"],
            },
            "long_text_equal_tail": tail_exp["result"]["model_input_equal"],
            "long_text_equal_head": head_exp["result"]["model_input_equal"],
            "long_text_tail": {
                "experiment_id": tail_exp_id,
                "baseline_tokens": tail_exp["result"]["baseline"]["prediction"]["token_count_before_truncation"],
                "variant_tokens": tail_exp["result"]["variant"]["prediction"]["token_count_before_truncation"],
                "truncated": tail_exp["result"]["baseline"]["prediction"]["truncated"],
                "model_input_equal": tail_exp["result"]["model_input_equal"],
                "warnings": tail_exp["result"]["warnings"],
            },
            "long_text_head": {
                "experiment_id": head_exp_id,
                "baseline_tokens": head_exp["result"]["baseline"]["prediction"]["token_count_before_truncation"],
                "variant_tokens": head_exp["result"]["variant"]["prediction"]["token_count_before_truncation"],
                "truncated": head_exp["result"]["baseline"]["prediction"]["truncated"],
                "model_input_equal": head_exp["result"]["model_input_equal"],
                "warnings": head_exp["result"]["warnings"],
            },
            "same_input_parity": {
                "model_input_equal": pair_same["model_input_equal"],
                "max_score_diff_pair": max_score_diff_pair,
                "max_score_diff_vs_predict": max_score_diff_vs_predict,
                "token_count_before_truncation": p_a["token_count_before_truncation"],
            },
            "export_id": export_id,
            "export_sha256": hashlib.sha256(export_bytes_before).hexdigest(),
            "screenshots": {
                "desktop": str(desktop_shot_path),
                "mobile_390": str(mobile_shot_path),
            },
        }
        report_json_text = json.dumps(diagnostic_payload, indent=2, ensure_ascii=False)
        (tmp_path / "real-model-three-layer.json").write_text(report_json_text, encoding="utf-8")
        extra_report_dir = os.environ.get("QA_M4_REPORT_DIR") or os.environ.get("QA_M4_SCREENSHOT_DIR")
        if extra_report_dir:
            extra_dir_path = Path(extra_report_dir)
            extra_dir_path.mkdir(parents=True, exist_ok=True)
            (extra_dir_path / "real-model-three-layer.json").write_text(report_json_text, encoding="utf-8")
    except Exception:
        for log_file in sorted(log_dir.glob("*.log")):
            tail = log_file.read_text(encoding="utf-8", errors="replace")[-3000:]
            print(f"\n--- {log_file.name} ---\n{tail}", file=sys.stderr)
        raise
    finally:
        _stop_stack(api_proc, worker_proc, api_log, worker_log)
