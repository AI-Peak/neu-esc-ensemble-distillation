"""Playwright E2E tests for M1 Topic Attention (T02), M2 Review Signals (T04), and M3 Sensitivity (T08).

Uses an explicit controlled software-test double (`ControlledE2ERegistry`) via
`--serve-controlled` subprocess on an ephemeral loopback port. Never represents
test doubles as live ED/PhoBERT/UIT model inference.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import socket
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

from tests.e2e.react_callbacks import invoke_bound_onclick

PROFILES = {
    p["id"]: p
    for p in json.loads(
        (ROOT / "services" / "profiles.json").read_text(encoding="utf-8-sig")
    )
}

# Exact controlled predictions for E2E scenarios: (profile, text) -> (sentiment_id, topic_id).
CONTROLLED_PREDICTIONS = {
    # --- NEU main ranking / Toxic / tie-breakers / n<5 / click-through dataset ---
    ("neu", "Ký túc xá phản hồi chậm khi hỏng điều hòa (ưu tiên)."): (2, 4),
    ("neu", "Thủ tục xác nhận sinh viên tại phòng dịch vụ mất nhiều thời gian."): (2, 4),
    ("neu", "Căng tin khu B phục vụ chậm vào giờ cao điểm (ưu tiên)."): (2, 4),
    ("neu", "Cổng thông tin dịch vụ trực tuyến cập nhật khá nhanh."): (1, 4),
    ("neu", "Bình luận thô lỗ nhắm vào nhân viên quầy dịch vụ."): (3, 4),
    ("neu", "Tin tuyển dụng thực tập thiếu thông tin mức hỗ trợ."): (2, 5),
    ("neu", "Hội thảo việc làm sắp lịch trùng giờ thi cuối kỳ."): (2, 5),
    ("neu", "Ngày hội việc làm kết nối nhiều doanh nghiệp uy tín."): (1, 5),
    ("neu", "Trung tâm hỗ trợ nghề nghiệp sửa CV rất tận tình."): (1, 5),
    ("neu", "Thông tin tuyển dụng khối tài chính năm nay đa dạng."): (1, 5),
    ("neu", "Sự kiện chào tân sinh viên âm thanh bị rè khó nghe."): (2, 9),
    ("neu", "Câu lạc bộ truyền thông thông báo đổi lịch quá gấp."): (2, 9),
    ("neu", "Danh sách câu lạc bộ mở đăng ký đầu học kỳ."): (0, 9),
    ("neu", "Đề cương môn kinh tế lượng thiếu ví dụ minh họa."): (2, 2),
    ("neu", "Giảng viên giải thích bài tập xác suất rất dễ hiểu."): (1, 2),
    ("neu", "Bài hỏi đáp học bổng bị trôi nhiều ngày chưa có phản hồi."): (2, 8),
    ("neu", "Kinh nghiệm đăng ký ký túc xá cho sinh viên khóa mới."): (0, 8),
    # --- NEU partial/error run dataset (items 1..8 pass in batch 1; 9..10 contain [FAIL]) ---
    ("neu", "Căng tin phục vụ chậm giờ trưa."): (2, 4),
    ("neu", "Phòng máy thiếu ghế vào ca chiều."): (2, 4),
    ("neu", "Wifi thư viện ổn định cả ngày."): (1, 4),
    ("neu", "Ngôn từ công kích trong nhóm học phần."): (3, 2),
    ("neu", "Tài liệu môn học cập nhật đầy đủ."): (1, 2),
    ("neu", "Bài tập nhóm môn xác suất hơi nặng."): (2, 2),
    ("neu", "Hội thao khoa tổ chức chu đáo."): (1, 9),
    ("neu", "Lịch thi học kỳ đã công bố."): (0, 1),
    # --- UIT schema dataset ---
    ("uit", "UIT: Giảng viên dạy chậm và khó hiểu phần hồi quy."): (0, 0),
    ("uit", "UIT: Giảng viên giải thích bài giảng rất nhiệt tình."): (2, 0),
    ("uit", "UIT: Máy chiếu phòng C201 hay bị tắt giữa giờ."): (0, 2),
    ("uit", "UIT: Chương trình đào tạo sắp xếp học phần hợp lý."): (1, 1),
}

NEU_MAIN_ITEMS = [
    {"text": "Ký túc xá phản hồi chậm khi hỏng điều hòa (ưu tiên)."},
    {"text": "Thủ tục xác nhận sinh viên tại phòng dịch vụ mất nhiều thời gian."},
    {"text": "Căng tin khu B phục vụ chậm vào giờ cao điểm (ưu tiên)."},
    {"text": "Cổng thông tin dịch vụ trực tuyến cập nhật khá nhanh."},
    {"text": "Bình luận thô lỗ nhắm vào nhân viên quầy dịch vụ."},
    {"text": "Tin tuyển dụng thực tập thiếu thông tin mức hỗ trợ."},
    {"text": "Hội thảo việc làm sắp lịch trùng giờ thi cuối kỳ."},
    {"text": "Ngày hội việc làm kết nối nhiều doanh nghiệp uy tín."},
    {"text": "Trung tâm hỗ trợ nghề nghiệp sửa CV rất tận tình."},
    {"text": "Thông tin tuyển dụng khối tài chính năm nay đa dạng."},
    {"text": "Sự kiện chào tân sinh viên âm thanh bị rè khó nghe."},
    {"text": "Câu lạc bộ truyền thông thông báo đổi lịch quá gấp."},
    {"text": "Danh sách câu lạc bộ mở đăng ký đầu học kỳ."},
    {"text": "Đề cương môn kinh tế lượng thiếu ví dụ minh họa."},
    {"text": "Giảng viên giải thích bài tập xác suất rất dễ hiểu."},
    {"text": "Bài hỏi đáp học bổng bị trôi nhiều ngày chưa có phản hồi."},
    {"text": "Kinh nghiệm đăng ký ký túc xá cho sinh viên khóa mới."},
]

NEU_PARTIAL_ERROR_ITEMS = [
    {"text": "Căng tin phục vụ chậm giờ trưa."},
    {"text": "Phòng máy thiếu ghế vào ca chiều."},
    {"text": "Wifi thư viện ổn định cả ngày."},
    {"text": "Ngôn từ công kích trong nhóm học phần."},
    {"text": "Tài liệu môn học cập nhật đầy đủ."},
    {"text": "Bài tập nhóm môn xác suất hơi nặng."},
    {"text": "Hội thao khoa tổ chức chu đáo."},
    {"text": "Lịch thi học kỳ đã công bố."},
    {"text": "Phản ánh lỗi hệ thống đăng ký môn học [FAIL]"},
    {"text": "Nội dung khác gặp sự cố nạp model [FAIL]"},
]

UIT_ITEMS = [
    {"text": "UIT: Giảng viên dạy chậm và khó hiểu phần hồi quy."},
    {"text": "UIT: Giảng viên giải thích bài giảng rất nhiệt tình."},
    {"text": "UIT: Máy chiếu phòng C201 hay bị tắt giữa giờ."},
    {"text": "UIT: Chương trình đào tạo sắp xếp học phần hợp lý."},
]


def _make_scores(count, weights):
    vec = [0.0] * count
    for idx, val in weights.items():
        vec[idx] = val
    assert abs(sum(vec) - 1.0) < 1e-9, f"Scores must sum to 1.0, got {sum(vec)}"
    return vec


EXPECTED_CSV_COLUMNS = [
    "item_id", "source_row", "text", "metadata", "revision_id", "revision", "schema_id",
    "selected_run_id", "prediction_status", "prediction_id", "run_id", "model_id", "model_version",
    "label_source", "selected_sentiment", "selected_topic", "ai_sentiment", "ai_topic",
    "sentiment_scores", "topic_scores", "reference_sentiment", "reference_sentiment_source",
    "reference_topic", "reference_topic_source", "review_sentiment", "review_sentiment_status",
    "review_sentiment_revision", "review_sentiment_note", "review_sentiment_source_prediction_id",
    "review_topic", "review_topic_status", "review_topic_revision", "review_topic_note",
    "review_topic_source_prediction_id", "effective_sentiment", "effective_topic",
    "token_count_before_truncation", "truncated", "warnings", "error",
]

# Controlled probability vectors and truncation metadata for T04 E2E tests.
# Never represent these test doubles as real model calibration or inference.
S1_SENT_FLAG_TEXT = "S1: Cảm xúc phân vân (LOW_TOP1 chỉ ở cảm xúc)."
S2_TOPIC_FLAG_TEXT = "S2: Chủ đề phân vân (LOW_TOP1 và SMALL_MARGIN ở chủ đề)."
S3_TRUNCATED_TEXT = "S3: Văn bản dài bị cắt ngắn nhưng điểm hai tác vụ đều rõ."
S4_CLEAR_TEXT = "S4: Dự đoán rõ cả hai tác vụ và không bị cắt ngắn."
S5_CORRUPT_TEXT = "S5: Dòng để thử dữ liệu điểm bị hỏng trong SQLite."
S6_NOPRED_TEXT = "S6: Phản hồi thêm sau để chưa có dự đoán AI."
N1_QUEUE_TEXT = "N1: Phản hồi đầu tiên có cảm xúc phân vân cho Lưu và câu tiếp theo."
N2_QUEUE_TEXT = "N2: Phản hồi thứ hai có chủ đề phân vân cho Lưu và câu tiếp theo."
N3_QUEUE_CLEAR_TEXT = "N3: Phản hồi thứ ba rõ ràng không nằm trong hàng chờ tín hiệu."
C1_CONFLICT_TEXT = "C1: Phản hồi gắn cờ cảm xúc để thử xung đột hai tab và xuất CSV."
C2_EXPORT_TEXT = "C2: Phản hồi gắn cờ chủ đề xuất hiện trong xuất lọc tín hiệu."
C3_EXPORT_CLEAR_TEXT = "C3: Phản hồi rõ ràng chỉ xuất hiện khi xuất toàn bộ."

_CLEAR_NEU_SENTIMENT = {
    "label_id": 1,
    "scores": _make_scores(4, {1: 0.85, 0: 0.05, 2: 0.05, 3: 0.05}),
}
_CLEAR_NEU_SENTIMENT_NEG = {
    "label_id": 2,
    "scores": _make_scores(4, {2: 0.85, 0: 0.05, 1: 0.05, 3: 0.05}),
}
_CLEAR_NEU_TOPIC_4 = {
    "label_id": 4,
    "scores": _make_scores(
        10, {4: 0.82, 2: 0.10, 0: 0.01, 1: 0.01, 3: 0.01, 5: 0.01, 6: 0.01, 7: 0.01, 8: 0.01, 9: 0.01}
    ),
}
_CLEAR_NEU_TOPIC_2 = {
    "label_id": 2,
    "scores": _make_scores(
        10, {2: 0.82, 4: 0.10, 0: 0.01, 1: 0.01, 3: 0.01, 5: 0.01, 6: 0.01, 7: 0.01, 8: 0.01, 9: 0.01}
    ),
}
_CLEAR_NEU_TOPIC_9 = {
    "label_id": 9,
    "scores": _make_scores(
        10, {9: 0.82, 4: 0.10, 0: 0.01, 1: 0.01, 2: 0.01, 3: 0.01, 5: 0.01, 6: 0.01, 7: 0.01, 8: 0.01}
    ),
}
_FLAGGED_SENT_LOW_TOP1 = {
    "label_id": 2,
    "scores": _make_scores(4, {2: 0.55, 0: 0.25, 1: 0.10, 3: 0.10}),
}
_FLAGGED_SENT_BOTH = {
    "label_id": 2,
    "scores": _make_scores(4, {2: 0.45, 3: 0.40, 0: 0.10, 1: 0.05}),
}
_FLAGGED_TOPIC_BOTH = {
    "label_id": 5,
    "scores": _make_scores(
        10, {5: 0.48, 8: 0.42, 0: 0.02, 1: 0.02, 2: 0.01, 3: 0.01, 4: 0.01, 6: 0.01, 7: 0.01, 9: 0.01}
    ),
}

CONTROLLED_SIGNAL_SPECS = {
    ("neu", S1_SENT_FLAG_TEXT): {
        "sentiment": _FLAGGED_SENT_LOW_TOP1,
        "topic": _CLEAR_NEU_TOPIC_4,
    },
    ("neu", S2_TOPIC_FLAG_TEXT): {
        "sentiment": _CLEAR_NEU_SENTIMENT_NEG,
        "topic": _FLAGGED_TOPIC_BOTH,
    },
    ("neu", S3_TRUNCATED_TEXT): {
        "sentiment": _CLEAR_NEU_SENTIMENT,
        "topic": _CLEAR_NEU_TOPIC_2,
        "truncated": True,
        "token_count_before_truncation": 156,
        "warnings": ["INPUT_TRUNCATED"],
    },
    ("neu", S4_CLEAR_TEXT): {
        "sentiment": _CLEAR_NEU_SENTIMENT,
        "topic": _CLEAR_NEU_TOPIC_9,
    },
    ("neu", S5_CORRUPT_TEXT): {
        "sentiment": _CLEAR_NEU_SENTIMENT,
        "topic": _CLEAR_NEU_TOPIC_4,
    },
    ("neu", S6_NOPRED_TEXT): {
        "sentiment": _CLEAR_NEU_SENTIMENT,
        "topic": _CLEAR_NEU_TOPIC_9,
    },
    ("neu", N1_QUEUE_TEXT): {
        "sentiment": _FLAGGED_SENT_LOW_TOP1,
        "topic": _CLEAR_NEU_TOPIC_4,
    },
    ("neu", N2_QUEUE_TEXT): {
        "sentiment": _CLEAR_NEU_SENTIMENT_NEG,
        "topic": _FLAGGED_TOPIC_BOTH,
    },
    ("neu", N3_QUEUE_CLEAR_TEXT): {
        "sentiment": _CLEAR_NEU_SENTIMENT,
        "topic": _CLEAR_NEU_TOPIC_9,
    },
    ("neu", C1_CONFLICT_TEXT): {
        "sentiment": _FLAGGED_SENT_BOTH,
        "topic": _CLEAR_NEU_TOPIC_4,
    },
    ("neu", C2_EXPORT_TEXT): {
        "sentiment": _CLEAR_NEU_SENTIMENT_NEG,
        "topic": _FLAGGED_TOPIC_BOTH,
    },
    ("neu", C3_EXPORT_CLEAR_TEXT): {
        "sentiment": _CLEAR_NEU_SENTIMENT,
        "topic": _CLEAR_NEU_TOPIC_9,
    },
}

# Controlled sensitivity pair test doubles (M3/T08). Strictly synthetic software test doubles;
# never real ED/PhoBERT/UIT model probabilities or tokenizations.
M3_SWITCH_TEXT = "Dịch vụ phòng đào tạo rất tốt và hỗ trợ nhanh."
M3_SWITCH_VARIANT = "Dịch vụ phòng đào tạo  và hỗ trợ nhanh."
M3_REPEAT_TEXT = "Giảng viên tốt nhưng cách phản hồi tốt vẫn cần tốt hơn."
M3_REPEAT_VARIANT_SECOND = "Giảng viên tốt nhưng cách phản hồi  vẫn cần tốt hơn."
M3_OVERLAP_TEXT = "ababa là mã học phần thử nghiệm."
M3_OVERLAP_VARIANT_SECOND = "ab là mã học phần thử nghiệm."
M3_UNICODE_TEXT = "Hỗ trợ 🎉 nhiệt tình\nnhưng phòng hơi nóng."
M3_UNICODE_VARIANT = "Hỗ trợ 🎉 nhiệt tình\nnhưng phòng ."
M3_NFD_TEXT = "Ca\u0301n bộ hỗ trợ nhiệt tình."
M3_TRUNC_TEXT = (
    "Phần đầu cần thử "
    + " ".join(["nội"] * 132)
    + " phần cuối bị cắt."
)
M3_TRUNC_VARIANT_END = "Phần đầu cần thử " + " ".join(["nội"] * 132)
M3_TRUNC_VARIANT_START = " ".join(["nội"] * 132) + " phần cuối bị cắt."
M3_NOPRED_TEXT = "M3: Câu mới thêm rất ổn sau khi chạy."
M3_NOPRED_VARIANT = "M3: Câu mới thêm  sau khi chạy."
M3_PAIR_INVALID_TEXT = "M3: Phản hồi kiểm tra lỗi nửa cặp [PAIR_INVALID] kết thúc."
M3_SLOW_TEXT = "M3: Văn bản chậm [SLOW_PAIR] để kiểm hủy và polling."
M3_RACE_TEXT = "M3: Văn bản kiểm thử độ trễ và hủy tác vụ."
M3_SECOND_ITEM_TEXT = "M3: Phản hồi thứ hai khi chuyển câu."

_M3_SENT_POS = {
    "label_id": 1,
    "scores": _make_scores(4, {0: 0.06, 1: 0.72, 2: 0.16, 3: 0.06}),
}
_M3_SENT_NEG_SWITCH = {
    "label_id": 2,
    "scores": _make_scores(4, {0: 0.12, 1: 0.23, 2: 0.58, 3: 0.07}),
}
_M3_SENT_POS_VARIANT_UNCHANGED = {
    "label_id": 1,
    "scores": _make_scores(4, {0: 0.06, 1: 0.65, 2: 0.23, 3: 0.06}),
}
_M3_TOPIC_4_BASE = {
    "label_id": 4,
    "scores": _make_scores(
        10,
        {4: 0.78, 2: 0.08, 0: 0.02, 1: 0.02, 3: 0.02, 5: 0.02, 6: 0.02, 7: 0.02, 8: 0.01, 9: 0.01},
    ),
}
_M3_TOPIC_2_SWITCH = {
    "label_id": 2,
    "scores": _make_scores(
        10,
        {2: 0.62, 4: 0.20, 0: 0.02, 1: 0.02, 3: 0.02, 5: 0.02, 6: 0.02, 7: 0.02, 8: 0.03, 9: 0.03},
    ),
}
_M3_TOPIC_2_ALT = {
    "label_id": 2,
    "scores": _make_scores(
        10,
        {2: 0.74, 4: 0.12, 0: 0.02, 1: 0.02, 3: 0.02, 5: 0.02, 6: 0.02, 7: 0.02, 8: 0.01, 9: 0.01},
    ),
}

CONTROLLED_SIGNAL_SPECS.update(
    {
        ("neu", M3_SWITCH_TEXT): {
            "sentiment": _M3_SENT_POS,
            "topic": _M3_TOPIC_4_BASE,
        },
        ("neu", M3_REPEAT_TEXT): {
            "sentiment": _M3_SENT_POS,
            "topic": _M3_TOPIC_2_ALT,
        },
        ("neu", M3_OVERLAP_TEXT): {
            "sentiment": _CLEAR_NEU_SENTIMENT,
            "topic": _CLEAR_NEU_TOPIC_2,
        },
        ("neu", M3_UNICODE_TEXT): {
            "sentiment": _M3_SENT_POS,
            "topic": _M3_TOPIC_4_BASE,
        },
        ("neu", M3_NFD_TEXT): {
            "sentiment": _CLEAR_NEU_SENTIMENT,
            "topic": _CLEAR_NEU_TOPIC_4,
        },
        ("neu", M3_TRUNC_TEXT): {
            "sentiment": _M3_SENT_POS,
            "topic": _M3_TOPIC_4_BASE,
            "truncated": True,
            "token_count_before_truncation": 139,
            "warnings": ["INPUT_TRUNCATED"],
        },
        ("neu", M3_PAIR_INVALID_TEXT): {
            "sentiment": _CLEAR_NEU_SENTIMENT,
            "topic": _CLEAR_NEU_TOPIC_4,
        },
        ("neu", M3_SLOW_TEXT): {
            "sentiment": _CLEAR_NEU_SENTIMENT,
            "topic": _CLEAR_NEU_TOPIC_4,
        },
        ("neu", M3_RACE_TEXT): {
            "sentiment": _CLEAR_NEU_SENTIMENT,
            "topic": _CLEAR_NEU_TOPIC_4,
        },
        ("neu", M3_SECOND_ITEM_TEXT): {
            "sentiment": _CLEAR_NEU_SENTIMENT,
            "topic": _CLEAR_NEU_TOPIC_9,
        },
    }
)

CONTROLLED_PAIR_SPECS = {
    ("neu", M3_SWITCH_TEXT, M3_SWITCH_VARIANT): {
        "baseline": {"sentiment": _M3_SENT_POS, "topic": _M3_TOPIC_4_BASE},
        "variant": {"sentiment": _M3_SENT_NEG_SWITCH, "topic": _M3_TOPIC_2_SWITCH},
        "model_input_equal": False,
    },
    ("neu", M3_REPEAT_TEXT, M3_REPEAT_VARIANT_SECOND): {
        "baseline": {"sentiment": _M3_SENT_POS, "topic": _M3_TOPIC_2_ALT},
        "variant": {"sentiment": _M3_SENT_POS_VARIANT_UNCHANGED, "topic": _M3_TOPIC_2_ALT},
        "model_input_equal": False,
    },
    ("neu", M3_OVERLAP_TEXT, M3_OVERLAP_VARIANT_SECOND): {
        "baseline": {"sentiment": _CLEAR_NEU_SENTIMENT, "topic": _CLEAR_NEU_TOPIC_2},
        "variant": {"sentiment": _M3_SENT_POS_VARIANT_UNCHANGED, "topic": _CLEAR_NEU_TOPIC_2},
        "model_input_equal": False,
    },
    ("neu", M3_UNICODE_TEXT, M3_UNICODE_VARIANT): {
        "baseline": {"sentiment": _M3_SENT_POS, "topic": _M3_TOPIC_4_BASE},
        "variant": {"sentiment": _M3_SENT_NEG_SWITCH, "topic": _M3_TOPIC_4_BASE},
        "model_input_equal": False,
    },
    ("neu", M3_TRUNC_TEXT, M3_TRUNC_VARIANT_END): {
        "baseline": {
            "sentiment": _M3_SENT_POS,
            "topic": _M3_TOPIC_4_BASE,
            "truncated": True,
            "token_count_before_truncation": 139,
            "warnings": ["INPUT_TRUNCATED"],
        },
        "variant": {
            "sentiment": _M3_SENT_POS,
            "topic": _M3_TOPIC_4_BASE,
            "truncated": True,
            "token_count_before_truncation": 135,
            "warnings": ["INPUT_TRUNCATED"],
        },
        "model_input_equal": True,
    },
    ("neu", M3_TRUNC_TEXT, M3_TRUNC_VARIANT_START): {
        "baseline": {
            "sentiment": _M3_SENT_POS,
            "topic": _M3_TOPIC_4_BASE,
            "truncated": True,
            "token_count_before_truncation": 139,
            "warnings": ["INPUT_TRUNCATED"],
        },
        "variant": {
            "sentiment": _M3_SENT_NEG_SWITCH,
            "topic": _M3_TOPIC_2_SWITCH,
            "truncated": True,
            "token_count_before_truncation": 135,
            "warnings": ["INPUT_TRUNCATED"],
        },
        "model_input_equal": False,
    },
    ("neu", M3_NOPRED_TEXT, M3_NOPRED_VARIANT): {
        "baseline": {"sentiment": _M3_SENT_POS, "topic": _M3_TOPIC_4_BASE},
        "variant": {"sentiment": _M3_SENT_NEG_SWITCH, "topic": _M3_TOPIC_4_BASE},
        "model_input_equal": False,
    },
}


class ControlledE2ERegistry:
    """Explicit controlled software-test double. Never live model evidence."""

    __test__ = False

    def status(self, profile):
        return {
            "available": True,
            "reason": None,
            "model_id": "TEST-DOUBLE-E2E-CONTROLLED",
            "model_version": "software-test-double-v1",
            "schema_id": PROFILES[profile]["schema_id"],
        }

    def execution_identity(self, profile):
        if profile not in PROFILES:
            raise ValueError(f"Unknown profile: {profile}")
        return {
            "profile": profile,
            "schema_id": PROFILES[profile]["schema_id"],
            "model_id": "TEST-DOUBLE-E2E-CONTROLLED",
            "model_version": "software-test-double-v1",
            "manifest_sha256": "e2e-controlled-manifest-sha256",
            "preprocessing_sha256": "e2e-controlled-preprocessing-sha256",
            "mode": "cpu-fp32-eval",
        }

    def _build_prediction(self, profile, item, spec_override=None):
        meta = self.status(profile)
        key = (profile, item["text"])
        spec = spec_override or CONTROLLED_SIGNAL_SPECS.get(key)
        if spec is not None:
            return {
                "model_id": meta["model_id"],
                "model_version": meta["model_version"],
                "schema_id": meta["schema_id"],
                "item_id": item["item_id"],
                "revision_id": item["revision_id"],
                "duration_ms": 0.05,
                "token_count_before_truncation": spec.get(
                    "token_count_before_truncation",
                    len(item["text"].split()) + 2,
                ),
                "truncated": bool(spec.get("truncated", False)),
                "warnings": list(spec.get("warnings", [])),
                "sentiment": {
                    "label_id": spec["sentiment"]["label_id"],
                    "scores": list(spec["sentiment"]["scores"]),
                },
                "topic": {
                    "label_id": spec["topic"]["label_id"],
                    "scores": list(spec["topic"]["scores"]),
                },
            }
        if key in CONTROLLED_PREDICTIONS:
            sent_id, topic_id = CONTROLLED_PREDICTIONS[key]
            prediction = {
                "model_id": meta["model_id"],
                "model_version": meta["model_version"],
                "schema_id": meta["schema_id"],
                "item_id": item["item_id"],
                "revision_id": item["revision_id"],
                "duration_ms": 0.05,
                "token_count_before_truncation": len(item["text"].split()) + 2,
                "truncated": False,
                "warnings": [],
            }
            for task, winner in (("sentiment", sent_id), ("topic", topic_id)):
                count = len(PROFILES[profile][task])
                scores = [0.1 / (count - 1)] * count
                scores[winner] = 0.9
                prediction[task] = {"label_id": winner, "scores": scores}
            return prediction
        raise KeyError(f"Unmapped controlled E2E text: {key!r}")

    def predict(self, profile, items):
        for item in items:
            if "[FAIL]" in item["text"]:
                raise RuntimeError("Controlled E2E batch inference failure")
        return [self._build_prediction(profile, item) for item in items]

    def predict_pair(self, profile, items, expected_identity):
        if len(items) != 2:
            raise ValueError("Controlled pair requires 2 items")
        identity = self.execution_identity(profile)
        if expected_identity != identity:
            raise RuntimeError("Execution identity mismatch in controlled pair")
        if "[SLOW_PAIR]" in items[0]["text"] or "[SLOW_PAIR]" in items[1]["text"]:
            time.sleep(2.0)
        if "[PAIR_INVALID]" in items[0]["text"] or "[PAIR_INVALID]" in items[1]["text"]:
            # Intentionally return only 1 item (pair_bad) to verify Worker INVALID_PAIR_RESULT handling.
            first_pred = self._build_prediction(
                profile,
                items[0],
                spec_override={"sentiment": _CLEAR_NEU_SENTIMENT, "topic": _CLEAR_NEU_TOPIC_4},
            )
            return {
                "predictions": [first_pred],
                "execution_identity": identity,
                "model_input_equal": False,
            }
        pair_key = (profile, items[0]["text"], items[1]["text"])
        pair_spec = CONTROLLED_PAIR_SPECS.get(pair_key)
        if pair_spec is not None:
            baseline_pred = self._build_prediction(
                profile, items[0], spec_override=pair_spec["baseline"]
            )
            variant_pred = self._build_prediction(
                profile, items[1], spec_override=pair_spec["variant"]
            )
            return {
                "predictions": [baseline_pred, variant_pred],
                "execution_identity": identity,
                "model_input_equal": bool(pair_spec["model_input_equal"]),
            }
        default_spec = {"sentiment": _CLEAR_NEU_SENTIMENT, "topic": _CLEAR_NEU_TOPIC_4}
        baseline_pred = self._build_prediction(profile, items[0], spec_override=default_spec)
        variant_pred = self._build_prediction(profile, items[1], spec_override=default_spec)
        return {
            "predictions": [baseline_pred, variant_pred],
            "execution_identity": identity,
            "model_input_equal": False,
        }


class ControlledTestServer:
    __test__ = False

    def __init__(self, runtime):
        self.runtime = runtime
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.process = None
        self.log_path = self.runtime.parent / f"{self.runtime.name}-server.log"

    def start(self):
        args = [
            sys.executable,
            __file__,
            "--serve-controlled",
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
                    "Controlled E2E API exited early: "
                    + self.log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                )
            try:
                if httpx.get(self.url + "/api/v1/health", timeout=0.5).is_success:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self.stop()
        raise TimeoutError("Controlled E2E API did not become ready")

    def stop(self):
        if self.process is not None:
            if os.name == "nt" and self.process.poll() is None:
                subprocess.run(
                    ["taskkill.exe", "/PID", str(self.process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            elif self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None


@pytest.fixture
def controlled_server(tmp_path):
    server = ControlledTestServer(tmp_path / "controlled-e2e-runtime").start()
    yield server
    server.stop()


def track_errors(page):
    page_errors = []
    console_errors = []
    page.on("pageerror", lambda err: page_errors.append(str(err)))
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    return page_errors, console_errors


def wait_for_run_terminal(client, dataset_id, timeout_seconds=20):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        runs = client.get(f"/datasets/{dataset_id}/analysis-runs").json()
        if runs and runs[0]["status"] in (
            "completed",
            "completed_with_errors",
            "failed",
            "cancelled",
        ):
            return runs[0]
        time.sleep(0.1)
    raise AssertionError("Controlled analysis run did not finish within timeout")


def read_attention_rows(page):
    expect(page.locator(".attention-table tbody tr").first).to_be_visible()
    rows = []
    trs = page.locator(".attention-table tbody tr")
    for idx in range(trs.count()):
        tr = trs.nth(idx)
        cells = tr.locator("td")
        topic_name = tr.locator(".attention-topic-name").inner_text().strip()
        badge_count = tr.locator(".attention-topic-cell .badge").count()
        badge = (
            tr.locator(".attention-topic-cell .badge").first.inner_text().strip()
            if badge_count
            else None
        )
        neg = cells.nth(1).inner_text().strip()
        eligible_text = cells.nth(2).inner_text().strip()
        rate = cells.nth(3).inner_text().strip()
        cell_count = cells.count()
        toxic = cells.nth(4).inner_text().strip() if cell_count == 6 else None
        btn = tr.locator("button.attention-evidence-btn")
        rows.append(
            {
                "topic": topic_name,
                "badge": badge,
                "negative": neg,
                "eligible": eligible_text,
                "rate": rate,
                "toxic": toxic,
                "btn_text": btn.inner_text().strip(),
                "btn_disabled": btn.is_disabled(),
            }
        )
    return rows


def assert_no_horizontal_overflow(page, label=""):
    ok = page.evaluate(
        "document.documentElement.scrollWidth <= window.innerWidth + 1"
    )
    assert ok, (
        f"Horizontal overflow detected ({label}): "
        + str(
            page.evaluate(
                "({scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth})"
            )
        )
    )


def prepare_screenshot(page):
    try:
        toast_close = page.locator(".toast button").first
        if toast_close.is_visible():
            toast_close.click(timeout=500)
    except Exception:
        pass
    page.evaluate("window.scrollTo(0, 0)")


def test_t02_neu_attention_viewports_keyboard_filters_reviews_and_sources(
    browser, controlled_server, screenshot_dir
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "NEU Khảo sát học kỳ 1",
            "profile": "neu",
            "items": NEU_MAIN_ITEMS,
        },
    ).json()

    # 1. Desktop 1440x960: analyze in UI, verify ranking, Toxic, ties, n<5, viewports, keyboard, filters, reviews.
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")
    expect(
        page.get_by_role("heading", name="NEU Khảo sát học kỳ 1", exact=True)
    ).to_be_visible()

    # Before analysis: empty state (no fake table).
    expect(page.get_by_role("heading", name="Chủ đề cần chú ý", exact=True)).to_be_visible()
    expect(
        page.get_by_text(
            "Chưa đủ nhãn để tính theo chủ đề. Chạy phân tích hoặc duyệt nhãn thủ công.",
            exact=True,
        )
    ).to_be_visible()
    assert page.locator(".attention-table").count() == 0

    # Trigger controlled AI analysis from UI and wait for completion.
    page.get_by_test_id("analyze").click()
    expect(page.get_by_text("17/17 kết quả đã lưu", exact=True)).to_be_visible(
        timeout=20000
    )
    run_id = client.get(f"/datasets/{ds['id']}/analysis-runs").json()[0]["id"]

    # Verify NEU table: Toxic separated, tie-breaks (negative_count DESC -> eligible_count DESC -> topic_id ASC), small_sample < 5.
    expect(page.locator(".attention-table thead")).to_contain_text("Toxic")
    expect(page.locator(".attention-denominator")).to_contain_text(
        "Mẫu số: 17/17 dòng có đủ cả chủ đề và cảm xúc"
    )
    rows = read_attention_rows(page)
    assert [r["topic"] for r in rows] == [
        "Dịch vụ",
        "Việc làm / tuyển dụng",
        "Câu lạc bộ / sự kiện",
        "Học tập",
        "Hỏi đáp / chia sẻ",
    ]
    assert rows[0] == {
        "topic": "Dịch vụ",
        "badge": None,
        "negative": "3",
        "eligible": "5",
        "rate": "3/5 · 60,0%",
        "toxic": "1",
        "btn_text": "Xem 3 phản hồi tiêu cực",
        "btn_disabled": False,
    }
    assert rows[1] == {
        "topic": "Việc làm / tuyển dụng",
        "badge": None,
        "negative": "2",
        "eligible": "5",
        "rate": "2/5 · 40,0%",
        "toxic": "0",
        "btn_text": "Xem 2 phản hồi tiêu cực",
        "btn_disabled": False,
    }
    assert rows[2]["badge"] == "Ít dữ liệu"
    assert rows[2]["rate"] == "2/3 · 66,7%"
    assert rows[3]["badge"] == "Ít dữ liệu" and rows[3]["rate"] == "1/2 · 50,0%"
    assert rows[4]["badge"] == "Ít dữ liệu" and rows[4]["rate"] == "1/2 · 50,0%"
    assert_no_horizontal_overflow(page, "1440x960")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "m1-desktop-overview.png"), full_page=True)

    # Laptop 1024x768 screenshot + overflow check
    page.set_viewport_size({"width": 1024, "height": 768})
    expect(page.locator(".attention-table")).to_be_visible()
    assert_no_horizontal_overflow(page, "1024x768")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "m1-laptop-overview.png"), full_page=True)

    # Mobile 390x844 screenshot + overflow + stacked card view check
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator(".attention-table thead")).not_to_be_visible()
    assert_no_horizontal_overflow(page, "390x844")
    prepare_screenshot(page)
    page.screenshot(
        path=str(screenshot_dir / "m1-mobile-390-overview.png"), full_page=True
    )

    # Mobile 320x568 screenshot + overflow check
    page.set_viewport_size({"width": 320, "height": 568})
    expect(page.locator(".attention-table thead")).not_to_be_visible()
    assert_no_horizontal_overflow(page, "320x568")
    prepare_screenshot(page)
    page.screenshot(
        path=str(screenshot_dir / "m1-mobile-320-overview.png"), full_page=True
    )

    # Restore desktop viewport for interaction & keyboard tests
    page.set_viewport_size({"width": 1440, "height": 960})

    # Keyboard focus + Enter on first evidence button (Dịch vụ) after setting a custom sort to ensure drill-down resets sort
    # Also verify changing sort does not refetch /summary or unmount TopicAttention (Finding 2 regression guard)
    first_btn = page.get_by_role(
        "button", name="Xem 3 phản hồi tiêu cực của chủ đề Dịch vụ", exact=True
    )
    summary_requests_on_sort = []
    def _track_summary_req(req):
        if "/summary" in req.url:
            summary_requests_on_sort.append(req.url)
    page.on("request", _track_summary_req)
    with page.expect_response(lambda r: "/items" in r.url and "sort=text" in r.url and r.ok):
        page.get_by_label("Sắp xếp phản hồi", exact=True).select_option("text")
        assert first_btn.count() == 1
    page.remove_listener("request", _track_summary_req)
    assert summary_requests_on_sort == []
    page.get_by_label("Lần phân tích", exact=True).select_option(run_id)
    expect(first_btn).to_be_visible()
    page.get_by_label("Lần phân tích", exact=True).focus()
    for _ in range(5):
        page.keyboard.press("Tab")
        if first_btn.evaluate("el => el === document.activeElement"):
            break
    expect(first_btn).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.get_by_role("tab", name="Tất cả phản hồi", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    expect(page.get_by_label("Lọc chủ đề", exact=True)).to_have_value("4")
    expect(page.get_by_label("Lọc cảm xúc", exact=True)).to_have_value("2")
    expect(page.get_by_label("Sắp xếp phản hồi", exact=True)).to_have_value(
        "source_row"
    )
    expect(page.get_by_role("button", name="Đổi sang giảm dần", exact=True)).to_be_visible()
    expect(page.get_by_label("Lần phân tích", exact=True)).to_have_value(run_id)
    expect(page.locator(".items-section h2")).to_contain_text("(3)")
    item_rows = [
        page.locator(".item-table tbody tr").nth(i).locator("td").first.inner_text().strip()
        for i in range(3)
    ]
    assert item_rows == ["1", "2", "3"]
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "m1-filtered-items.png"), full_page=True)

    # Bỏ lọc clears topic/sentiment while preserving label_source and run_id
    page.get_by_role("button", name=re.compile(r"^Bỏ lọc \(2\)$")).click()
    expect(page.get_by_label("Lọc chủ đề", exact=True)).to_have_value("")
    expect(page.get_by_label("Lọc cảm xúc", exact=True)).to_have_value("")
    expect(page.get_by_label("Lần phân tích", exact=True)).to_have_value(run_id)
    expect(page.locator(".items-section h2")).to_contain_text("(17)")

    # Switch to Tổng quan & test Spacebar activation on second evidence button (Việc làm / tuyển dụng)
    page.get_by_role("tab", name="Tổng quan", exact=True).click()
    second_btn = page.get_by_role(
        "button",
        name="Xem 2 phản hồi tiêu cực của chủ đề Việc làm / tuyển dụng",
        exact=True,
    )
    first_btn.focus()
    page.keyboard.press("Tab")
    expect(second_btn).to_be_focused()
    page.keyboard.press(" ")
    expect(page.get_by_role("tab", name="Tất cả phản hồi", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    expect(page.get_by_label("Lọc chủ đề", exact=True)).to_have_value("5")
    expect(page.get_by_label("Lọc cảm xúc", exact=True)).to_have_value("2")
    expect(page.locator(".items-section h2")).to_contain_text("(2)")

    # Reset back to current text & clear filters
    page.get_by_role("button", name=re.compile(r"^Bỏ lọc \(2\)$")).click()
    page.get_by_label("Lần phân tích", exact=True).select_option("")
    page.get_by_role("tab", name="Tổng quan", exact=True).click()

    # Preserving q and review_status across click-through ("Xem N phản hồi tiêu cực")
    # Confirm item 1 ("Ký túc xá ... (ưu tiên).") with both labels so review_status="unreviewed" isolates item 3.
    item1 = client.get(f"/datasets/{ds['id']}/items", params={"q": "Ký túc xá phản hồi chậm"}).json()["items"][0]
    page.get_by_role("button", name=item1["text"], exact=True).click()
    page.get_by_label("Trạng thái cảm xúc", exact=True).select_option("confirmed")
    page.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    expect(
        page.get_by_test_id("review-sentiment").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    page.get_by_label("Trạng thái chủ đề", exact=True).select_option("confirmed")
    page.get_by_role("button", name="Lưu chủ đề", exact=True).click()
    expect(
        page.get_by_test_id("review-topic").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    page.get_by_label("Tìm nội dung", exact=True).fill("ưu tiên")
    expect(page.locator(".attention-denominator")).to_contain_text("Mẫu số: 2/2")
    page.get_by_label("Lọc trạng thái rà soát", exact=True).select_option("unreviewed")
    expect(page.locator(".attention-denominator")).to_contain_text("Mẫu số: 1/1")
    page.get_by_role(
        "button", name="Xem 1 phản hồi tiêu cực của chủ đề Dịch vụ", exact=True
    ).click()
    expect(page.get_by_role("tab", name="Tất cả phản hồi", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    expect(page.get_by_label("Tìm nội dung", exact=True)).to_have_value("ưu tiên")
    expect(page.get_by_label("Lọc trạng thái rà soát", exact=True)).to_have_value(
        "unreviewed"
    )
    expect(page.get_by_label("Lọc chủ đề", exact=True)).to_have_value("4")
    expect(page.get_by_label("Lọc cảm xúc", exact=True)).to_have_value("2")
    expect(page.locator(".items-section h2")).to_contain_text("(1)")
    expect(page.locator(".item-table tbody tr")).to_have_count(1)
    expect(page.locator(".item-table tbody tr").first).to_contain_text(
        "Căng tin khu B phục vụ chậm"
    )
    # Remove filters & return to Overview
    page.get_by_role("button", name=re.compile(r"^Bỏ lọc \(4\)$")).click()
    expect(page.locator(".items-section h2")).to_contain_text("(17)")
    page.get_by_role("tab", name="Tổng quan", exact=True).click()

    # Conditional sentiment filter notices & 0-Negative state
    page.get_by_label("Lọc cảm xúc", exact=True).select_option("1")  # Positive
    expect(
        page.get_by_text(
            "Đang lọc cảm xúc; tỷ lệ không mô tả toàn bộ bộ phản hồi.", exact=True
        )
    ).to_be_visible()
    expect(
        page.get_by_text(
            "Chưa có phản hồi gán nhãn Tiêu cực trong phạm vi đang xem.", exact=True
        )
    ).to_be_visible()
    evidence_btns = page.locator("button.attention-evidence-btn")
    assert evidence_btns.count() > 0
    for idx in range(evidence_btns.count()):
        expect(evidence_btns.nth(idx)).to_be_disabled()
        expect(evidence_btns.nth(idx)).to_have_text("Xem 0 phản hồi tiêu cực")

    # Filtering Negative (2) STILL shows the conditional filter warning banner
    page.get_by_label("Lọc cảm xúc", exact=True).select_option("2")
    expect(
        page.get_by_text(
            "Đang lọc cảm xúc; tỷ lệ không mô tả toàn bộ bộ phản hồi.", exact=True
        )
    ).to_be_visible()
    expect(
        page.get_by_text(
            "Chưa có phản hồi gán nhãn Tiêu cực trong phạm vi đang xem.", exact=True
        )
    ).not_to_be_visible()
    expect(
        page.get_by_role(
            "button", name="Xem 3 phản hồi tiêu cực của chủ đề Dịch vụ", exact=True
        )
    ).to_be_enabled()
    page.get_by_role("button", name=re.compile(r"^Bỏ lọc \(1\)$")).click()

    # Requirement (b): Edit sentiment (Negative -> Positive) & edit topic on items -> updates effective while ai stays unchanged
    item2_text = "Thủ tục xác nhận sinh viên tại phòng dịch vụ mất nhiều thời gian."
    item3_text = "Căng tin khu B phục vụ chậm vào giờ cao điểm (ưu tiên)."
    for target_text in (item2_text, item3_text):
        page.get_by_role("button", name=target_text, exact=True).click()
        page.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
        page.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("1")
        page.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
        expect(
            page.get_by_test_id("review-sentiment").get_by_text("Đã lưu · bản duyệt 1", exact=True)
        ).to_be_visible()
        page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # Dịch vụ dropped from 3 Negative to 1 Negative -> falls below Việc làm / tuyển dụng (2) & Câu lạc bộ / sự kiện (2),
    # and stays above Học tập & Hỏi đáp / chia sẻ on tie negative=1 because Dịch vụ has higher eligible_count (5 > 2)!
    rows_after_sent = read_attention_rows(page)
    assert [r["topic"] for r in rows_after_sent] == [
        "Việc làm / tuyển dụng",
        "Câu lạc bộ / sự kiện",
        "Dịch vụ",
        "Học tập",
        "Hỏi đáp / chia sẻ",
    ]
    dich_vu_row = next(r for r in rows_after_sent if r["topic"] == "Dịch vụ")
    assert dich_vu_row["negative"] == "1" and dich_vu_row["rate"] == "1/5 · 20,0%"

    # Edit topic on item3 from Dịch vụ (4) -> Chuyện cá nhân (6): Dịch vụ drops to eligible 4 (Ít dữ liệu) and Chuyện cá nhân appears!
    page.get_by_role("button", name=item3_text, exact=True).click()
    page.get_by_label("Trạng thái chủ đề", exact=True).select_option("corrected")
    page.get_by_label("Nhãn chủ đề đã sửa", exact=True).select_option("6")
    page.get_by_role("button", name="Lưu chủ đề", exact=True).click()
    expect(
        page.get_by_test_id("review-topic").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    rows_after_topic = read_attention_rows(page)
    dich_vu_row = next(r for r in rows_after_topic if r["topic"] == "Dịch vụ")
    assert dich_vu_row["eligible"] == "4" and dich_vu_row["badge"] == "Ít dữ liệu"
    ca_nhan_row = next(r for r in rows_after_topic if r["topic"] == "Chuyện cá nhân")
    assert ca_nhan_row["negative"] == "0" and ca_nhan_row["eligible"] == "1"

    # Toggle Nguồn nhãn -> ai: original AI counts & ranking remain intact!
    source_select = page.locator(".source-controls label").first.locator("select")
    source_select.select_option("ai")
    expect(page.locator(".attention-header")).to_contain_text("Chỉ dự đoán AI gốc")
    expect(page.locator(".attention-table tbody tr").first).to_contain_text("Dịch vụ")
    rows_ai = read_attention_rows(page)
    assert [r["topic"] for r in rows_ai] == [
        "Dịch vụ",
        "Việc làm / tuyển dụng",
        "Câu lạc bộ / sự kiện",
        "Học tập",
        "Hỏi đáp / chia sẻ",
    ]
    assert rows_ai[0]["negative"] == "3" and rows_ai[0]["eligible"] == "5"
    # Clicking evidence in AI mode preserves label_source="ai" and matches AI negative count
    page.get_by_role(
        "button", name="Xem 3 phản hồi tiêu cực của chủ đề Dịch vụ", exact=True
    ).click()
    expect(page.get_by_role("tab", name="Tất cả phản hồi", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    expect(source_select).to_have_value("ai")
    expect(page.locator(".items-section h2")).to_contain_text("(3)")
    page.get_by_role("button", name=re.compile(r"^Bỏ lọc \(2\)$")).click()
    source_select.select_option("effective")
    page.get_by_role("tab", name="Tổng quan", exact=True).click()

    # Add an unpredicted item and assign ONLY manual topic=1 (Tin tức) to test n=0, "—", and disabled button in UI!
    client.post(
        f"/datasets/{ds['id']}/items",
        json={"items": [{"text": "Lịch đăng ký tín chỉ bổ sung vừa được công bố."}]},
    )
    page.reload()
    page.get_by_role(
        "button", name="Lịch đăng ký tín chỉ bổ sung vừa được công bố.", exact=True
    ).click()
    page.get_by_label("Trạng thái chủ đề", exact=True).select_option("corrected")
    page.get_by_label("Nhãn chủ đề đã sửa", exact=True).select_option("1")
    page.get_by_role("button", name="Lưu chủ đề", exact=True).click()
    expect(
        page.get_by_test_id("review-topic").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    expect(page.locator(".attention-table")).to_contain_text("Tin tức")

    rows_with_zero_n = read_attention_rows(page)
    tin_tuc = next(r for r in rows_with_zero_n if r["topic"] == "Tin tức")
    assert tin_tuc["negative"] == "0"
    assert "0" in tin_tuc["eligible"] and "thiếu cảm xúc: 1" in tin_tuc["eligible"]
    assert tin_tuc["rate"] == "—"
    assert tin_tuc["badge"] == "Ít dữ liệu"
    assert tin_tuc["btn_disabled"] is True and tin_tuc["btn_text"] == "Xem 0 phản hồi tiêu cực"

    assert not page_errors
    assert not console_errors
    client.close()
    context.close()


def test_t02_uit_schema_has_no_toxic_and_maps_negative_id_zero(
    browser, controlled_server
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={"name": "UIT Đánh giá học phần", "profile": "uit", "items": UIT_ITEMS},
    ).json()

    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_test_id("analyze").click()
    expect(page.get_by_text("4/4 kết quả đã lưu", exact=True)).to_be_visible(
        timeout=20000
    )

    expect(page.locator(".attention-table thead")).not_to_contain_text("Toxic")
    expect(page.locator(".attention-rules")).not_to_contain_text("Toxic")
    rows = read_attention_rows(page)
    assert all(r["toxic"] is None for r in rows)
    assert [r["topic"] for r in rows] == [
        "Giảng viên",
        "Cơ sở vật chất",
        "Chương trình đào tạo",
    ]
    assert rows[0]["negative"] == "1" and rows[0]["rate"] == "1/2 · 50,0%"
    assert rows[1]["negative"] == "1" and rows[1]["rate"] == "1/1 · 100,0%"
    assert rows[2]["negative"] == "0" and rows[2]["btn_disabled"] is True

    # Click evidence on Giảng viên -> uses UIT negative ID 0!
    page.get_by_role(
        "button", name="Xem 1 phản hồi tiêu cực của chủ đề Giảng viên", exact=True
    ).click()
    expect(page.get_by_role("tab", name="Tất cả phản hồi", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    expect(page.get_by_label("Lọc cảm xúc", exact=True)).to_have_value("0")
    expect(page.get_by_label("Lọc chủ đề", exact=True)).to_have_value("0")
    expect(page.locator(".items-section h2")).to_contain_text("(1)")
    expect(page.locator(".item-table tbody tr").first).to_contain_text(
        "UIT: Giảng viên dạy chậm và khó hiểu phần hồi quy."
    )

    assert not page_errors
    assert not console_errors
    client.close()
    context.close()


def test_t02_no_label_and_partial_error_states(
    browser, missing_server, controlled_server, screenshot_dir
):
    # Part 1: Model unavailable -> no-label honest state, then manual 2-label review counts immediately
    missing_client = httpx.Client(base_url=missing_server.url + "/api/v1")
    ds_missing = missing_client.post(
        "/datasets",
        json={
            "name": "Bộ chưa có model",
            "profile": "neu",
            "items": [
                {"text": "Phản hồi đầu tiên chưa có nhãn."},
                {"text": "Phản hồi thứ hai chưa có nhãn."},
            ],
        },
    ).json()

    ctx1 = browser.new_context(viewport={"width": 1280, "height": 800})
    p1 = ctx1.new_page()
    err1, con1 = track_errors(p1)
    p1.goto(missing_server.url + f"/#/datasets/{ds_missing['id']}")
    expect(
        p1.get_by_text(
            "Chưa đủ nhãn để tính theo chủ đề. Chạy phân tích hoặc duyệt nhãn thủ công.",
            exact=True,
        )
    ).to_be_visible()
    assert p1.locator(".attention-table").count() == 0

    # Manual review of 2 labels works without a model -> appears in Overview with partial badge
    p1.get_by_role(
        "button", name="Phản hồi đầu tiên chưa có nhãn.", exact=True
    ).click()
    p1.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    p1.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("2")
    p1.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    expect(
        p1.get_by_test_id("review-sentiment").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    p1.get_by_label("Trạng thái chủ đề", exact=True).select_option("corrected")
    p1.get_by_label("Nhãn chủ đề đã sửa", exact=True).select_option("4")
    p1.get_by_role("button", name="Lưu chủ đề", exact=True).click()
    expect(
        p1.get_by_test_id("review-topic").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    p1.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    expect(p1.locator(".attention-section .badge").first).to_have_text("Kết quả một phần")
    expect(p1.locator(".attention-denominator")).to_contain_text(
        "Mẫu số: 1/2 dòng có đủ cả chủ đề và cảm xúc · 1 dòng thiếu chủ đề"
    )
    rows_manual = read_attention_rows(p1)
    assert len(rows_manual) == 1 and rows_manual[0]["topic"] == "Dịch vụ"
    assert rows_manual[0]["negative"] == "1" and rows_manual[0]["rate"] == "1/1 · 100,0%"
    assert not err1 and not con1
    missing_client.close()
    ctx1.close()

    # Part 2: Controlled run completes with errors (8/10 analyzed, 2 failed) + manual 2-label review on 1 failed item
    ctrl_client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds_err = ctrl_client.post(
        "/datasets",
        json={
            "name": "NEU Phiên phân tích có lỗi một phần",
            "profile": "neu",
            "items": NEU_PARTIAL_ERROR_ITEMS,
        },
    ).json()

    ctx2 = browser.new_context(viewport={"width": 1440, "height": 960})
    p2 = ctx2.new_page()
    err2, con2 = track_errors(p2)
    p2.goto(controlled_server.url + f"/#/datasets/{ds_err['id']}")
    p2.get_by_test_id("analyze").click()
    run = wait_for_run_terminal(ctrl_client, ds_err["id"])
    assert run["status"] == "completed_with_errors"
    expect(p2.get_by_text("8/10 kết quả đã lưu · 2 dòng lỗi", exact=True)).to_be_visible(
        timeout=15000
    )
    expect(p2.locator(".attention-section")).to_contain_text("Hoàn tất, có dòng lỗi")
    expect(p2.locator(".attention-denominator")).to_contain_text(
        "Mẫu số: 8/10 dòng có đủ cả chủ đề và cảm xúc · 2 dòng thiếu chủ đề"
    )

    # Manually assign both labels on one of the failed items (row 9)
    failed_text = "Phản ánh lỗi hệ thống đăng ký môn học [FAIL]"
    p2.locator("button.text-cell", has_text=failed_text).click()
    expect(p2.get_by_role("alert")).to_contain_text("Lỗi xử lý:")
    p2.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    p2.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("2")
    p2.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    expect(
        p2.get_by_test_id("review-sentiment").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    p2.get_by_label("Trạng thái chủ đề", exact=True).select_option("corrected")
    p2.get_by_label("Nhãn chủ đề đã sửa", exact=True).select_option("0")
    p2.get_by_role("button", name="Lưu chủ đề", exact=True).click()
    expect(
        p2.get_by_test_id("review-topic").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    p2.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # In effective mode, manually reviewed failed item IS counted (9/10); in ai mode it is NOT (8/10)
    expect(p2.locator(".attention-section")).to_contain_text(
        "9/10 dòng có đủ hai nhãn · 8/10 dòng đã phân tích · 2 dòng lỗi"
    )
    expect(p2.locator(".attention-denominator")).to_contain_text(
        "Mẫu số: 9/10 dòng có đủ cả chủ đề và cảm xúc · 1 dòng thiếu chủ đề"
    )
    rows_err_eff = read_attention_rows(p2)
    spam_row = next(r for r in rows_err_eff if r["topic"] == "Rác / quảng cáo")
    assert spam_row["negative"] == "1" and spam_row["eligible"] == "1"
    prepare_screenshot(p2)
    p2.screenshot(path=str(screenshot_dir / "m1-error-partial.png"), full_page=True)

    p2.locator(".source-controls label").first.locator("select").select_option("ai")
    expect(p2.locator(".attention-denominator")).to_contain_text(
        "Mẫu số: 8/10 dòng có đủ cả chủ đề và cảm xúc · 2 dòng thiếu chủ đề"
    )
    assert all(r["topic"] != "Rác / quảng cáo" for r in read_attention_rows(p2))

    assert not err2 and not con2
    ctrl_client.close()
    ctx2.close()


def test_t04_signals_review_independence_policy_details_and_rerun(
    browser, controlled_server
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "NEU Tín hiệu rà soát T04",
            "profile": "neu",
            "items": [
                {"text": S1_SENT_FLAG_TEXT},
                {"text": S2_TOPIC_FLAG_TEXT},
                {"text": S3_TRUNCATED_TEXT},
                {"text": S4_CLEAR_TEXT},
                {"text": S5_CORRUPT_TEXT},
            ],
        },
    ).json()

    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")

    page.get_by_test_id("analyze").click()
    expect(page.get_by_text("5/5 kết quả đã lưu", exact=True)).to_be_visible(
        timeout=20000
    )
    expect(page.locator(".job-strip strong")).to_have_text("Hoàn tất", timeout=20000)
    run1_id = client.get(f"/datasets/{ds['id']}/analysis-runs").json()[0]["id"]

    # Add unpredicted item (NO_PREDICTION) and corrupt S5's Run 1 payload in SQLite (INVALID_SCORES)
    s6_created = client.post(
        f"/datasets/{ds['id']}/items",
        json={"items": [{"text": S6_NOPRED_TEXT}]},
    ).json()
    assert len(s6_created) == 1

    conn = sqlite3.connect(controlled_server.runtime / "workspace.sqlite3", timeout=10.0)
    try:
        row = conn.execute(
            "SELECT p.id, p.payload FROM predictions p JOIN items i ON i.id = p.item_id JOIN revisions r ON r.id = p.revision_id WHERE i.dataset_id = ? AND r.text = ?",
            (ds["id"], S5_CORRUPT_TEXT),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[1])
        payload["sentiment"]["scores"] = []
        conn.execute(
            "UPDATE predictions SET payload = ? WHERE id = ?",
            (json.dumps(payload), row[0]),
        )
        conn.commit()
    finally:
        conn.close()

    # Reset run_id to current text view ("") so S6 (added after Run 1) is visible, and open Tất cả phản hồi
    page.reload()
    page.get_by_label("Lần phân tích", exact=True).select_option("")
    page.get_by_role("tab", name="Tất cả phản hồi", exact=True).click()
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(6)")

    # Verify table separates "Tín hiệu model" and "Rà soát" columns cleanly
    headers = [
        page.locator(".item-table thead th").nth(i).inner_text().strip()
        for i in range(6)
    ]
    assert headers == [
        "Dòng",
        "Nội dung phản hồi",
        "Cảm xúc",
        "Chủ đề",
        "Tín hiệu model",
        "Rà soát",
    ]

    def row_for(text):
        return page.locator(".item-table tbody tr").filter(
            has=page.locator("button.text-cell", has_text=text)
        )

    # Check initial badges per state and verify NO_PREDICTION / INVALID_SCORES never get .success
    expect(row_for(S1_SENT_FLAG_TEXT).locator("td").nth(4)).to_contain_text(
        "Model phân vân: cảm xúc"
    )
    expect(row_for(S2_TOPIC_FLAG_TEXT).locator("td").nth(4)).to_contain_text(
        "Model phân vân: chủ đề"
    )
    expect(row_for(S3_TRUNCATED_TEXT).locator("td").nth(4)).to_contain_text(
        "Đầu vào bị cắt ngắn"
    )
    expect(row_for(S4_CLEAR_TEXT).locator("td").nth(4)).to_have_text("Không có cờ")
    for unavail_text in (S5_CORRUPT_TEXT, S6_NOPRED_TEXT):
        sig_cell = row_for(unavail_text).locator("td").nth(4)
        expect(sig_cell).to_have_text("Chưa có tín hiệu điểm")
        badge = sig_cell.locator(".badge")
        expect(badge).to_have_class(re.compile(r"\bneutral\b"))
        assert "success" not in (badge.get_attribute("class") or "").split()
        expect(row_for(unavail_text).locator("td").nth(5)).to_have_text("Chưa rà soát")

    # Legacy "Cần rà soát" tab keeps needs_review (includes unreviewed clear S4, INVALID_SCORES S5, NO_PREDICTION S6)
    page.get_by_role("tab", name="Cần rà soát", exact=True).click()
    expect(page.get_by_label("Lọc trạng thái rà soát", exact=True)).to_have_value(
        "needs_review"
    )
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(6)")

    # Button "Có tín hiệu, chưa đối chiếu" switches to review_status=all + review_signal=pending_signal_review (S1, S2, S3)
    page.get_by_role("button", name="Có tín hiệu, chưa đối chiếu", exact=True).click()
    expect(page.get_by_label("Lọc trạng thái rà soát", exact=True)).to_have_value("all")
    expect(page.get_by_label("Lọc tín hiệu model", exact=True)).to_have_value(
        "pending_signal_review"
    )
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(3)")

    # Switch to All items briefly to check INVALID_SCORES & NO_PREDICTION details in ItemDetail
    page.get_by_role("button", name=re.compile(r"^Bỏ lọc \(1\)$")).click()
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(6)")

    page.get_by_role("button", name=S5_CORRUPT_TEXT, exact=True).click()
    s5_details = page.locator("details.signal-details")
    s5_details.locator("summary").click()
    expect(s5_details).to_contain_text("INVALID_SCORES")
    expect(
        page.locator(".signal-task-row").first.locator(".badge")
    ).not_to_have_class(re.compile(r"\bsuccess\b"))
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    page.get_by_role("button", name=S6_NOPRED_TEXT, exact=True).click()
    s6_details = page.locator("details.signal-details")
    s6_details.locator("summary").click()
    expect(s6_details).to_contain_text("NO_PREDICTION")
    expect(s6_details).to_contain_text("top1 < 0.60, margin < 0.15")
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # Open S1 (flagged sentiment LOW_TOP1=0.550, clear topic=0.820) and inspect policy & metrics
    s1_api = client.get(f"/datasets/{ds['id']}/items", params={"q": S1_SENT_FLAG_TEXT}).json()["items"][0]
    expected_hash_prefix = s1_api["review_signals"]["policy_hash"][:12]
    page.get_by_role("button", name=S1_SENT_FLAG_TEXT, exact=True).click()
    sig_sec = page.locator(".signal-section")
    expect(sig_sec.get_by_text("Ngưỡng thử nghiệm, chưa hiệu chuẩn", exact=True)).to_be_visible()
    expect(sig_sec).to_contain_text(
        "Tín hiệu tính từ dự đoán AI gốc của lần đang xem (giữ nguyên khi đổi Nguồn nhãn hoặc sau khi lưu rà soát)."
    )
    expect(sig_sec.locator(".signal-task-row").nth(0)).to_contain_text(
        "Model phân vân: cảm xúc"
    )
    expect(sig_sec.locator(".signal-task-row").nth(0)).to_contain_text(
        "Điểm cao nhất dưới ngưỡng"
    )
    expect(sig_sec.locator(".signal-task-row").nth(0)).to_contain_text(
        "Đối chiếu: Chưa rà soát tác vụ này"
    )
    expect(sig_sec.locator(".signal-task-row").nth(1)).to_contain_text("Không có cờ")
    expect(sig_sec.locator(".signal-task-row").nth(1)).to_contain_text(
        "Đối chiếu: Chưa rà soát tác vụ này"
    )

    s1_details = sig_sec.locator("details.signal-details")
    s1_details.locator("summary").click()
    expect(s1_details).to_contain_text(f"Chính sách: review-signals-v1 · Ngưỡng thử nghiệm, chưa hiệu chuẩn · hash {expected_hash_prefix}")
    expect(s1_details).to_contain_text("0.550 (ngưỡng < 0.60)")
    expect(s1_details).to_contain_text("0.250")
    expect(s1_details).to_contain_text("0.300 (ngưỡng < 0.15)")
    expect(s1_details).to_contain_text("0.820 (ngưỡng < 0.60)")

    # Confirm ONLY topic on S1 -> topic becomes current_prediction, sentiment STILL unreviewed -> S1 stays in pending_signal_review
    page.get_by_label("Trạng thái chủ đề", exact=True).select_option("confirmed")
    page.get_by_role("button", name="Lưu chủ đề", exact=True).click()
    expect(
        page.get_by_test_id("review-topic").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    expect(sig_sec.locator(".signal-task-row").nth(1)).to_contain_text(
        "Đối chiếu: Đã đối chiếu tín hiệu của dự đoán này"
    )
    expect(sig_sec.locator(".signal-task-row").nth(0)).to_contain_text(
        "Đối chiếu: Chưa rà soát tác vụ này"
    )
    expect(sig_sec).to_contain_text(
        "Trạng thái hàng chờ: còn tín hiệu chưa đối chiếu với dự đoán đang xem."
    )
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    page.get_by_label("Lọc tín hiệu model", exact=True).select_option("pending_signal_review")
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(3)")
    expect(row_for(S1_SENT_FLAG_TEXT)).to_be_visible()

    # Toggling label_source to AI keeps signal badges and ItemDetail signals unchanged
    source_select = page.locator(".source-controls label").first.locator("select")
    source_select.select_option("ai")
    expect(row_for(S1_SENT_FLAG_TEXT).locator("td").nth(4)).to_contain_text(
        "Model phân vân: cảm xúc"
    )
    page.get_by_role("button", name=S1_SENT_FLAG_TEXT, exact=True).click()
    expect(sig_sec.locator(".signal-task-row").nth(0)).to_contain_text(
        "Model phân vân: cảm xúc"
    )
    # Manually correct sentiment on S1 -> manual (no prediction binding) -> leaves pending_signal_review!
    page.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    page.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("1")
    page.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    expect(
        page.get_by_test_id("review-sentiment").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    expect(sig_sec.locator(".signal-task-row").nth(0)).to_contain_text(
        "Đối chiếu: Nhãn tự chọn (không gắn một lần chạy cụ thể)"
    )
    expect(sig_sec).to_contain_text(
        "Trạng thái hàng chờ: đã đối chiếu cho dự đoán đang xem; dấu hiệu trên dự đoán AI gốc vẫn được giữ."
    )
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    source_select.select_option("effective")

    # S1 left pending_signal_review (now S2, S3 = 2), yet remains in model_uncertain (S1, S2 = 2) with "Đã đối chiếu"!
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(2)")
    expect(row_for(S1_SENT_FLAG_TEXT)).to_have_count(0)
    page.get_by_label("Lọc tín hiệu model", exact=True).select_option("model_uncertain")
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(2)")
    expect(row_for(S1_SENT_FLAG_TEXT).locator("td").nth(4)).to_contain_text(
        "Model phân vân: cảm xúc"
    )
    expect(row_for(S1_SENT_FLAG_TEXT).locator("td").nth(4)).to_contain_text(
        "Đã đối chiếu"
    )

    # Truncated S3 needs BOTH tasks reviewed to leave pending_signal_review
    page.get_by_label("Lọc tín hiệu model", exact=True).select_option("pending_signal_review")
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(2)")
    page.locator("button.text-cell", has_text=S3_TRUNCATED_TEXT).click()
    expect(sig_sec.locator(".signal-truncated-row")).to_contain_text(
        "Đầu vào bị cắt ngắn"
    )
    page.get_by_label("Trạng thái cảm xúc", exact=True).select_option("confirmed")
    page.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    expect(
        page.get_by_test_id("review-sentiment").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    expect(sig_sec).to_contain_text(
        "Trạng thái hàng chờ: còn tín hiệu chưa đối chiếu với dự đoán đang xem."
    )
    page.get_by_label("Trạng thái chủ đề", exact=True).select_option("confirmed")
    page.get_by_role("button", name="Lưu chủ đề", exact=True).click()
    expect(
        page.get_by_test_id("review-topic").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    expect(sig_sec).to_contain_text(
        "Trạng thái hàng chờ: đã đối chiếu cho dự đoán đang xem"
    )
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(1)")  # Only S2 left

    # Confirm flagged topic on S2 in Run 1 -> pending_signal_review becomes 0
    page.get_by_role("button", name=S2_TOPIC_FLAG_TEXT, exact=True).click()
    page.get_by_label("Trạng thái chủ đề", exact=True).select_option("confirmed")
    page.get_by_role("button", name="Lưu chủ đề", exact=True).click()
    expect(
        page.get_by_test_id("review-topic").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(0)")

    # Trigger Run 2 -> creates new prediction IDs:
    # S2 (confirmed topic in Run 1) now shows "Đã duyệt ở dự đoán khác" and RE-ENTERS pending_signal_review,
    # whereas S1 (manual sentiment) stays "Nhãn tự chọn (không gắn một lần chạy cụ thể)"!
    page.get_by_test_id("analyze").click()
    expect(page.get_by_text("6/6 kết quả đã lưu", exact=True)).to_be_visible(
        timeout=20000
    )
    expect(page.locator(".job-strip strong")).to_have_text("Hoàn tất", timeout=20000)
    page.get_by_label("Lần phân tích", exact=True).select_option("")  # Current text view (resolves Run 2)
    page.get_by_label("Lọc tín hiệu model", exact=True).select_option("pending_signal_review")
    expect(row_for(S2_TOPIC_FLAG_TEXT)).to_be_visible()
    s2_id = client.get(
        f"/datasets/{ds['id']}/items", params={"q": S2_TOPIC_FLAG_TEXT}
    ).json()["items"][0]["id"]
    s2_run2_api = client.get(f"/items/{s2_id}").json()
    assert s2_run2_api["prediction"]["run_id"] != run1_id
    assert s2_run2_api["review_signals"]["topic"]["review_relation"] == "other_prediction"
    page.get_by_role("button", name=S2_TOPIC_FLAG_TEXT, exact=True).click()
    expect(sig_sec.locator(".signal-task-row").nth(1)).to_contain_text(
        "Đối chiếu: Đã duyệt ở dự đoán khác"
    )
    expect(sig_sec).to_contain_text(
        "Trạng thái hàng chờ: còn tín hiệu chưa đối chiếu với dự đoán đang xem."
    )
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # Switching run selector back to Run 1 restores "Đã đối chiếu tín hiệu của dự đoán này" on S2
    page.get_by_label("Lần phân tích", exact=True).select_option(run1_id)
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(0)")
    page.get_by_label("Lọc tín hiệu model", exact=True).select_option("all")
    page.get_by_role("button", name=S2_TOPIC_FLAG_TEXT, exact=True).click()
    expect(sig_sec.locator(".signal-task-row").nth(1)).to_contain_text(
        "Đối chiếu: Đã đối chiếu tín hiệu của dự đoán này"
    )
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # Verify S1's manual sentiment remained manual in Run 2 as well
    page.get_by_label("Lần phân tích", exact=True).select_option("")
    page.get_by_role("button", name=S1_SENT_FLAG_TEXT, exact=True).click()
    expect(sig_sec.locator(".signal-task-row").nth(0)).to_contain_text(
        "Đối chiếu: Nhãn tự chọn (không gắn một lần chạy cụ thể)"
    )
    expect(sig_sec.locator(".signal-task-row").nth(1)).to_contain_text(
        "Đối chiếu: Đã duyệt ở dự đoán khác"
    )

    assert not page_errors
    assert not console_errors
    client.close()
    context.close()


def test_t04_save_next_queue_empty_clear_filters_and_session_hydration(
    browser, controlled_server
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "NEU Hàng chờ Save & Next T04",
            "profile": "neu",
            "items": [
                {"text": N1_QUEUE_TEXT},
                {"text": N2_QUEUE_TEXT},
                {"text": N3_QUEUE_CLEAR_TEXT},
            ],
        },
    ).json()

    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    responses = []
    page.on("response", lambda r: responses.append((r.status, r.url)))

    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_test_id("analyze").click()
    expect(page.get_by_text("3/3 kết quả đã lưu", exact=True)).to_be_visible(
        timeout=20000
    )

    # Session hydration 1: legacy M1 sessionStorage missing review_signal -> defaults to "all"
    storage_key = f"feedback-filters-{ds['id']}"
    page.evaluate(
        """([key]) => {
            sessionStorage.setItem(key, JSON.stringify({
                run_id: "",
                label_source: "effective",
                q: "",
                sentiment: "",
                topic: "",
                review_status: "all",
                sort: "source_row",
                direction: "asc",
                page: 1,
                page_size: 25,
            }));
        }""",
        [storage_key],
    )
    page.reload()
    expect(page.get_by_label("Lọc tín hiệu model", exact=True)).to_have_value("all")
    expect(page.locator(".items-section h2")).to_contain_text("(3)")

    # Session hydration 2: invalid review_signal="bogus" -> normalizes to "all" without HTTP 422
    responses.clear()
    page.evaluate(
        """([key]) => {
            sessionStorage.setItem(key, JSON.stringify({
                run_id: "",
                label_source: "effective",
                q: "",
                sentiment: "",
                topic: "",
                review_status: "all",
                review_signal: "bogus",
                sort: "source_row",
                direction: "asc",
                page: 1,
                page_size: 25,
            }));
        }""",
        [storage_key],
    )
    page.reload()
    expect(page.get_by_label("Lọc tín hiệu model", exact=True)).to_have_value("all")
    expect(page.locator(".items-section h2")).to_contain_text("(3)")
    assert all(status != 422 for status, _ in responses), (
        f"Unexpected 422 response after reloading bogus session filter: {responses}"
    )

    # Filter queue via review tab button: N1 & N2 (total 2)
    page.get_by_role("tab", name="Cần rà soát", exact=True).click()
    page.get_by_role("button", name="Có tín hiệu, chưa đối chiếu", exact=True).click()
    expect(page.locator(".items-section h2")).to_contain_text("(2)")
    expect(page.locator(".item-table tbody tr")).to_have_count(2)

    # Open N1, confirm flagged sentiment, and click "Lưu và câu tiếp theo →":
    # N1 leaves the filter, and panel advances cleanly to N2 without skipping!
    page.get_by_role("button", name=N1_QUEUE_TEXT, exact=True).click()
    expect(page.locator("#detail-title")).to_have_text("Dòng 1")
    page.get_by_label("Trạng thái cảm xúc", exact=True).select_option("confirmed")
    page.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True).click()

    expect(page.locator("dialog.detail-panel")).to_be_visible()
    expect(page.locator("#detail-title")).to_have_text("Dòng 2")
    expect(page.locator(".original-text")).to_have_text(N2_QUEUE_TEXT)
    expect(page.locator(".items-section h2")).to_contain_text("(1)")

    # On N2 (last remaining item in queue), correct flagged topic and click "Lưu và câu tiếp theo →":
    # Panel closes gracefully, toast says queue is empty, and empty-state "Bỏ bộ lọc" appears.
    page.get_by_label("Trạng thái chủ đề", exact=True).select_option("corrected")
    page.get_by_label("Nhãn chủ đề đã sửa", exact=True).select_option("4")
    page.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True).click()

    expect(page.locator("dialog.detail-panel")).to_have_count(0)
    expect(
        page.get_by_text("Không còn phản hồi trong bộ lọc hiện tại.", exact=True)
    ).to_be_visible()
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(0)")
    expect(
        page.get_by_role("heading", name="Không có phản hồi trong bộ lọc này", exact=True)
    ).to_be_visible()

    # Empty-state "Bỏ bộ lọc" resets review_signal to "all" and exits review tab
    page.get_by_role("button", name="Bỏ bộ lọc", exact=True).click()
    expect(page.get_by_label("Lọc tín hiệu model", exact=True)).to_have_value("all")
    expect(page.get_by_role("tab", name="Tất cả phản hồi", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(3)")

    # Toolbar "Bỏ lọc (1)" also resets review_signal back to "all"
    page.get_by_label("Lọc tín hiệu model", exact=True).select_option("model_uncertain")
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(2)")
    page.get_by_role("button", name=re.compile(r"^Bỏ lọc \(1\)$")).click()
    expect(page.get_by_label("Lọc tín hiệu model", exact=True)).to_have_value("all")
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(3)")

    assert not page_errors
    assert not console_errors
    client.close()
    context.close()


def test_t04_two_tab_conflict_preserves_draft_and_export_modal_scope(
    browser, controlled_server
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "NEU Xung đột & Xuất CSV T04",
            "profile": "neu",
            "items": [
                {"text": C1_CONFLICT_TEXT},
                {"text": C2_EXPORT_TEXT},
                {"text": C3_EXPORT_CLEAR_TEXT},
            ],
        },
    ).json()

    all_items = client.get(f"/datasets/{ds['id']}/items").json()["items"]
    id_by_text = {item["text"]: item["id"] for item in all_items}

    ctx_a = browser.new_context(viewport={"width": 1440, "height": 960}, accept_downloads=True)
    ctx_b = browser.new_context(viewport={"width": 1440, "height": 960})
    page_a = ctx_a.new_page()
    page_b = ctx_b.new_page()
    err_a, con_a = track_errors(page_a)
    err_b, con_b = track_errors(page_b)

    page_a.goto(controlled_server.url + f"/#/datasets/{ds['id']}")
    page_a.get_by_test_id("analyze").click()
    expect(page_a.get_by_text("3/3 kết quả đã lưu", exact=True)).to_be_visible(
        timeout=20000
    )

    page_b.goto(controlled_server.url + f"/#/datasets/{ds['id']}")
    page_a.get_by_role("tab", name="Tất cả phản hồi", exact=True).click()
    page_b.get_by_role("tab", name="Tất cả phản hồi", exact=True).click()

    # Open flagged item C1 in both tabs simultaneously
    page_a.get_by_role("button", name=C1_CONFLICT_TEXT, exact=True).click()
    page_b.get_by_role("button", name=C1_CONFLICT_TEXT, exact=True).click()

    # Draft in Tab A before saving
    page_a.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    page_a.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("1")
    page_a.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Bản nháp giữ lại từ tab A"
    )

    # Save first in Tab B
    page_b.get_by_label("Trạng thái cảm xúc", exact=True).select_option("confirmed")
    page_b.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Bản server từ tab B"
    )
    page_b.get_by_role("button", name="Lưu cảm xúc", exact=True).click()
    expect(
        page_b.get_by_test_id("review-sentiment").get_by_text("Đã lưu · bản duyệt 1", exact=True)
    ).to_be_visible()

    # Tab A clicks Save -> 409 conflict without losing draft label or note
    save_btn = page_a.get_by_role("button", name="Lưu cảm xúc", exact=True)
    with page_a.expect_response(
        lambda r: r.request.method == "PUT" and "/review" in r.url
    ) as conflict_resp:
        save_btn.click()
    assert conflict_resp.value.status == 409

    conflict_box = page_a.get_by_test_id("review-conflict-sentiment")
    expect(conflict_box).to_be_visible()
    expect(conflict_box).to_contain_text("Bản server từ tab B")
    expect(page_a.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("corrected")
    expect(page_a.get_by_label("Nhãn cảm xúc đã sửa", exact=True)).to_have_value("1")
    expect(
        page_a.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)
    ).to_have_value("Bản nháp giữ lại từ tab A")
    expect(save_btn).to_be_disabled()

    # Reapply draft on server revision & save
    page_a.get_by_role("button", name="Áp lại bản nháp: cảm xúc", exact=True).click()
    expect(save_btn).to_be_enabled()
    save_btn.click()
    expect(
        page_a.get_by_test_id("review-sentiment").get_by_text("Đã lưu · bản duyệt 2", exact=True)
    ).to_be_visible()
    expect(page_a.locator(".signal-task-row").nth(0)).to_contain_text(
        "Đối chiếu: Nhãn tự chọn (không gắn một lần chạy cụ thể)"
    )
    page_a.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # Export modal under review_signal="model_uncertain": verify copy, filtered vs all membership, and 40 CSV columns
    page_a.get_by_label("Lọc tín hiệu model", exact=True).select_option("model_uncertain")
    expect(page_a.locator(".items-section .section-heading h2")).to_contain_text("(2)")
    page_a.get_by_test_id("export").click()

    modal = page_a.locator("dialog.modal")
    expect(modal).to_contain_text(
        "CSV giữ các cột hiện có; tín hiệu tự động không có cột riêng."
    )
    expect(modal).to_contain_text(
        "“Toàn bộ” bỏ các bộ lọc tìm kiếm, nhãn, trạng thái rà soát và tín hiệu model."
    )
    scope_select = modal.get_by_role("combobox", name="Phạm vi xuất", exact=True)
    expect(scope_select).to_have_value("filtered")

    modal.get_by_role("button", name="Tạo bản chụp CSV", exact=True).click()
    expect(modal).to_contain_text("Đã tạo CSV: 2 dòng")
    with page_a.expect_download() as dl_filtered:
        modal.get_by_role("link", name="Tải CSV", exact=True).click()
    raw_filtered = Path(dl_filtered.value.path()).read_text(encoding="utf-8-sig")
    reader_filtered = csv.DictReader(raw_filtered.splitlines())
    assert reader_filtered.fieldnames == EXPECTED_CSV_COLUMNS
    rows_filtered = list(reader_filtered)
    assert {r["item_id"] for r in rows_filtered} == {
        id_by_text[C1_CONFLICT_TEXT],
        id_by_text[C2_EXPORT_TEXT],
    }

    # Switch export scope to "all" -> drops review_signal and includes C3 too
    scope_select.select_option("all")
    modal.get_by_role("button", name="Tạo bản chụp mới", exact=True).click()
    expect(modal).to_contain_text("Đã tạo CSV: 3 dòng")
    with page_a.expect_download() as dl_all:
        modal.get_by_role("link", name="Tải CSV", exact=True).click()
    raw_all = Path(dl_all.value.path()).read_text(encoding="utf-8-sig")
    reader_all = csv.DictReader(raw_all.splitlines())
    assert reader_all.fieldnames == EXPECTED_CSV_COLUMNS
    rows_all = list(reader_all)
    assert {r["item_id"] for r in rows_all} == {
        id_by_text[C1_CONFLICT_TEXT],
        id_by_text[C2_EXPORT_TEXT],
        id_by_text[C3_EXPORT_CLEAR_TEXT],
    }

    assert not err_a
    # Chromium logs one console error specifically for the intentional HTTP 409 conflict request.
    assert [m for m in con_a if "409 (Conflict)" not in m] == []
    assert len([m for m in con_a if "409 (Conflict)" in m]) == 1
    assert not err_b and not con_b
    client.close()
    ctx_a.close()
    ctx_b.close()


def test_t04_responsive_keyboard_accessibility_and_screenshots(
    browser, controlled_server, screenshot_dir
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "NEU Ảnh & Khả năng truy cập T04",
            "profile": "neu",
            "items": [
                {"text": S1_SENT_FLAG_TEXT},
                {"text": S2_TOPIC_FLAG_TEXT},
                {"text": S3_TRUNCATED_TEXT},
                {"text": S4_CLEAR_TEXT},
            ],
        },
    ).json()

    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")

    page.get_by_test_id("analyze").click()
    expect(page.get_by_text("4/4 kết quả đã lưu", exact=True)).to_be_visible(
        timeout=20000
    )
    # Add 5th unpredicted item (NO_PREDICTION) so all badge categories appear in one table
    client.post(
        f"/datasets/{ds['id']}/items",
        json={"items": [{"text": S6_NOPRED_TEXT}]},
    )
    page.reload()
    page.get_by_label("Lần phân tích", exact=True).select_option("")
    page.get_by_role("tab", name="Tất cả phản hồi", exact=True).click()
    expect(page.locator(".items-section .section-heading h2")).to_contain_text("(5)")

    # Keyboard control on Lọc tín hiệu model (focus + ArrowDown moves to "model_uncertain")
    sig_select = page.get_by_label("Lọc tín hiệu model", exact=True)
    sig_select.focus()
    expect(sig_select).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(sig_select).to_have_value("model_uncertain")
    expect(page.locator(".items-section h2")).to_contain_text("(2)")
    page.get_by_role("button", name=re.compile(r"^Bỏ lọc \(1\)$")).click()
    expect(page.locator(".items-section h2")).to_contain_text("(5)")

    # Desktop 1440x960 screenshot of Workspace with 6 columns & signal badges
    assert_no_horizontal_overflow(page, "1440x960 signals workspace")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "m2-desktop-signals.png"), full_page=True)

    # Keyboard open S1 detail via Enter, toggle "Vì sao được đánh dấu?" via Enter, inspect, then Escape
    s1_btn = page.get_by_role("button", name=S1_SENT_FLAG_TEXT, exact=True)
    s1_btn.focus()
    page.keyboard.press("Enter")
    detail_dialog = page.locator("dialog.detail-panel")
    expect(detail_dialog).to_be_visible()

    why_summary = detail_dialog.locator("details.signal-details summary")
    why_summary.focus()
    expect(why_summary).to_be_focused()
    page.keyboard.press("Enter")
    expect(detail_dialog.locator("details.signal-details")).to_have_attribute("open", "")
    detail_dialog.locator(".signal-section").scroll_into_view_if_needed()
    assert detail_dialog.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "m2-detail-signals.png"), full_page=False)

    # Escape closes dialog and restores focus to S1 trigger button
    page.keyboard.press("Escape")
    expect(detail_dialog).to_have_count(0)
    expect(s1_btn).to_be_focused()

    # Laptop 1024x768 check (workspace + ItemDetail with open details)
    page.set_viewport_size({"width": 1024, "height": 768})
    assert_no_horizontal_overflow(page, "1024x768 signals workspace")
    s1_btn.click()
    expect(detail_dialog).to_be_visible()
    detail_dialog.locator("details.signal-details summary").click()
    assert detail_dialog.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # Mobile 390x844 check + screenshot (stacked cards show "Tín hiệu model" label, filter controls fit cleanly)
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator(".item-table thead")).not_to_be_visible()
    expect(page.locator(".item-table td[data-label='Tín hiệu model']").first).to_be_visible()
    assert_no_horizontal_overflow(page, "390x844 signals workspace")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "m2-mobile-390-signals.png"), full_page=True)

    # Check ItemDetail at 390x844 too (signal metrics + details open)
    page.get_by_role("button", name=S1_SENT_FLAG_TEXT, exact=True).click()
    detail_dialog.locator("details.signal-details summary").click()
    expect(detail_dialog.locator("details.signal-details")).to_have_attribute("open", "")
    assert detail_dialog.evaluate("el => el.scrollWidth <= el.clientWidth + 1"), (
        "Horizontal overflow in detail dialog at 390x844"
    )
    assert_no_horizontal_overflow(page, "390x844 detail")
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # Mobile 320x568 check + screenshot
    page.set_viewport_size({"width": 320, "height": 568})
    expect(page.locator(".item-table thead")).not_to_be_visible()
    assert_no_horizontal_overflow(page, "320x568 signals workspace")
    prepare_screenshot(page)
    page.screenshot(path=str(screenshot_dir / "m2-mobile-320-signals.png"), full_page=True)

    # Check ItemDetail at 320x568 too
    page.get_by_role("button", name=S1_SENT_FLAG_TEXT, exact=True).click()
    detail_dialog.locator("details.signal-details summary").click()
    assert detail_dialog.evaluate("el => el.scrollWidth <= el.clientWidth + 1"), (
        "Horizontal overflow in detail dialog at 320x568"
    )
    assert_no_horizontal_overflow(page, "320x568 detail")
    page.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    assert not page_errors
    assert not console_errors
    client.close()
    context.close()


def _save_m3_screenshot(page, screenshot_dir, filename):
    target = screenshot_dir / filename
    page.screenshot(path=str(target), full_page=False)
    extra_dir = os.environ.get("QA_M3_SCREENSHOT_DIR")
    if extra_dir:
        extra_path = Path(extra_dir)
        extra_path.mkdir(parents=True, exist_ok=True)
        (extra_path / filename).write_bytes(target.read_bytes())


def _utf16_span(full_text, needle, occurrence=0):
    search_from = 0
    found = -1
    for _ in range(occurrence + 1):
        found = full_text.find(needle, search_from)
        assert found != -1, f"Substring {needle!r} occurrence {occurrence} not found in {full_text!r}"
        search_from = found + 1
    start_utf16 = len(full_text[:found].encode("utf-16-le")) // 2
    end_utf16 = len(full_text[: found + len(needle)].encode("utf-16-le")) // 2
    return start_utf16, end_utf16


def _select_raw_text_utf16(detail_dialog, start_utf16, end_utf16):
    raw_p = detail_dialog.locator("p.sensitivity-raw-text")
    raw_p.evaluate(
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


def _assert_expected_console_only(page_errors, console_errors, allowed_substrings=()):
    assert not page_errors, f"Unexpected pageerror(s): {page_errors}"
    unexpected = [
        msg
        for msg in console_errors
        if not any(token in msg for token in allowed_substrings)
    ]
    assert not unexpected, f"Unexpected console.error(s): {unexpected}"


def test_t08_desktop_direct_selection_switch_delta_immutability_and_screenshot(
    browser, controlled_server, screenshot_dir
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "M3 Desktop Sensitivity",
            "profile": "neu",
            "items": [
                {"text": M3_SWITCH_TEXT},
                {"text": M3_SECOND_ITEM_TEXT},
            ],
        },
    ).json()

    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_test_id("analyze").click()
    expect(page.get_by_text("2/2 kết quả đã lưu", exact=True)).to_be_visible(
        timeout=20000
    )

    items_before = client.get(f"/datasets/{ds['id']}/items").json()["items"]
    switch_item = next(i for i in items_before if i["text"] == M3_SWITCH_TEXT)
    summary_before = client.get(f"/datasets/{ds['id']}/summary").json()
    export_before = client.post(
        f"/datasets/{ds['id']}/exports",
        json={"scope": "all", "label_source": "effective"},
    ).json()
    export_bytes_before = client.get(f"/exports/{export_before['id']}").content

    # Open ItemDetail and enter an unsaved review draft before opening sensitivity panel
    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")
    expect(detail).to_be_visible()
    detail.get_by_label("Trạng thái cảm xúc", exact=True).select_option("corrected")
    detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True).select_option("0")
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Nháp rà soát trước khi thử độ nhạy"
    )

    panel = detail.locator("details.sensitivity-panel")
    expect(panel).not_to_have_attribute("open", "")
    panel.locator("summary").click()
    expect(panel).to_have_attribute("open", "")

    # Direct desktop selection on single text node inside .sensitivity-raw-text
    start_u16, end_u16 = _utf16_span(M3_SWITCH_TEXT, "rất tốt")
    _select_raw_text_utf16(detail, start_u16, end_u16)
    expect(
        detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True)
    ).to_have_value("rất tốt")
    expect(detail.locator(".sensitivity-variant-preview")).to_have_text(
        M3_SWITCH_VARIANT
    )

    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    results = detail.locator(".sensitivity-results")
    expect(results).to_be_visible(timeout=20000)

    # Fixed non-causal warning & absence of "Áp dụng biến thể"
    expect(results).to_contain_text(
        "Thử nghiệm độ nhạy: thay đổi đầu vào có thể làm thay đổi nghĩa; đây không phải bằng chứng chắc chắn về nguyên nhân model dự đoán."
    )
    assert (
        detail.get_by_role("button", name=re.compile(r"Áp dụng biến thể", re.I)).count()
        == 0
    )

    # Same-label delta tables (sentiment 4 labels & topic 10 labels), leader switch badges, 3 decimal formatting
    task_blocks = results.locator(".sensitivity-task-block")
    sent_block = task_blocks.nth(0)
    topic_block = task_blocks.nth(1)
    expect(sent_block).to_contain_text("Đổi nhãn dẫn đầu: Tích cực → Tiêu cực")
    expect(topic_block).to_contain_text("Đổi nhãn dẫn đầu: Dịch vụ → Học tập")

    # Initially collapsed: only 2 highlighted rows per switched task
    expect(sent_block.locator("tbody tr")).to_have_count(2)
    expect(topic_block.locator("tbody tr")).to_have_count(2)
    expect(sent_block.locator("tbody")).to_contain_text("0.720")
    expect(sent_block.locator("tbody")).to_contain_text("0.230")
    expect(sent_block.locator("tbody")).to_contain_text("-0.490")
    expect(sent_block.locator("tbody")).to_contain_text("+0.420")
    expect(sent_block.locator("tbody")).to_contain_text("Dẫn đầu gốc")
    expect(sent_block.locator("tbody")).to_contain_text("Dẫn đầu sau bỏ")

    # Toggle 4 sentiment labels & 10 topic labels
    sent_block.get_by_role("button", name="Xem tất cả 4 nhãn", exact=True).click()
    expect(sent_block.locator("tbody tr")).to_have_count(4)
    topic_block.get_by_role("button", name="Xem tất cả 10 nhãn", exact=True).click()
    expect(topic_block.locator("tbody tr")).to_have_count(10)
    topic_block.get_by_role(
        "button", name="Thu gọn chỉ xem nhãn dẫn đầu", exact=True
    ).click()
    expect(topic_block.locator("tbody tr")).to_have_count(2)

    # Take clean desktop screenshot with expanded sentiment table & topic delta table visible
    results.scroll_into_view_if_needed()
    assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert_no_horizontal_overflow(page, "1440x960 sensitivity detail")
    prepare_screenshot(page)
    _save_m3_screenshot(page, screenshot_dir, "m3-desktop-sensitivity.png")

    # Pre-typed review draft untouched & browser storage clean
    expect(
        detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)
    ).to_have_value("Nháp rà soát trước khi thử độ nhạy")
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value(
        "corrected"
    )
    expect(detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True)).to_have_value("0")
    storage_state = page.evaluate(
        """() => ({
            localLen: window.localStorage.length,
            sessionKeys: Object.keys(window.sessionStorage)
        })"""
    )
    assert storage_state["localLen"] == 0
    assert all("sensitivity" not in k.lower() for k in storage_state["sessionKeys"])

    # Source item text, prediction, reviews, summary, and existing export remain immutable
    item_after = client.get(f"/items/{switch_item['id']}").json()
    assert item_after["text"] == switch_item["text"]
    assert item_after["prediction"] == switch_item["prediction"]
    assert item_after["reviews"] == switch_item["reviews"]
    assert client.get(f"/datasets/{ds['id']}/summary").json() == summary_before
    assert client.get(f"/exports/{export_before['id']}").content == export_bytes_before
    assert not client.get("/datasets").json() == []
    assert len(client.get("/datasets").json()) == 1  # Temp sensitivity dataset hidden

    assert not page_errors
    assert not console_errors
    client.close()
    context.close()


def test_t08_occurrences_unchanged_truncation_unicode_and_no_prediction(
    browser, controlled_server
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "M3 Occurrences Truncation NoPred",
            "profile": "neu",
            "items": [
                {"text": M3_REPEAT_TEXT},
                {"text": M3_OVERLAP_TEXT},
                {"text": M3_UNICODE_TEXT},
                {"text": M3_NFD_TEXT},
                {"text": M3_TRUNC_TEXT},
            ],
        },
    ).json()

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")
    page.get_by_test_id("analyze").click()
    expect(page.get_by_text("5/5 kết quả đã lưu", exact=True)).to_be_visible(
        timeout=20000
    )

    # Add unpredicted item after analysis run and switch back to current texts view
    client.post(f"/datasets/{ds['id']}/items", json={"items": [{"text": M3_NOPRED_TEXT}]})
    page.reload()
    page.get_by_label("Lần phân tích", exact=True).select_option("")
    expect(page.get_by_role("button", name=M3_NOPRED_TEXT, exact=True)).to_be_visible()

    detail = page.locator("dialog.detail-panel")

    # 1. Repeated occurrence ("tốt"): error before picking radio -> focus first radio -> pick Lần 2/3 -> unchanged leader + 0.000
    page.get_by_role("button", name=M3_REPEAT_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    query_input = detail.get_by_label(
        "Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True
    )
    query_input.fill("tốt")
    radios = detail.locator("fieldset.sensitivity-occurrences input[type='radio']")
    expect(radios).to_have_count(3)
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(
        detail.get_by_text(
            "Đoạn này xuất hiện 3 lần. Chọn một vị trí cụ thể bên dưới trước khi chạy thử.",
            exact=True,
        )
    ).to_be_visible()
    expect(radios.first).to_be_focused()
    radios.nth(1).check()
    expect(detail.locator(".sensitivity-variant-preview")).to_have_text(
        M3_REPEAT_VARIANT_SECOND
    )
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    results = detail.locator(".sensitivity-results")
    expect(results).to_be_visible(timeout=20000)
    expect(results).to_contain_text("Nhãn dẫn đầu không đổi: Tích cực")
    expect(results).to_contain_text("Dẫn đầu gốc & sau bỏ")
    results.locator(".sensitivity-task-block").first.get_by_role(
        "button", name="Xem tất cả 4 nhãn", exact=True
    ).click()
    sent_rows_text = results.locator(".sensitivity-task-block").first.locator("tbody").inner_text()
    assert "-0.000" not in sent_rows_text and "+0.000" not in sent_rows_text
    assert "0.000" in sent_rows_text
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # 2. Overlapping occurrences ("aba" in "ababa ...") -> picks Lần 2/2 cleanly
    page.get_by_role("button", name=M3_OVERLAP_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label(
        "Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True
    ).fill("aba")
    overlap_radios = detail.locator(
        "fieldset.sensitivity-occurrences input[type='radio']"
    )
    expect(overlap_radios).to_have_count(2)
    overlap_radios.nth(1).check()
    expect(detail.locator(".sensitivity-variant-preview")).to_have_text(
        M3_OVERLAP_VARIANT_SECOND
    )
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # 3. Direct UTF-16 selection after emoji surrogate pair + newline
    page.locator(".item-table tbody tr", has_text="nhưng phòng hơi nóng.").locator(
        "button"
    ).first.click()
    detail.locator("details.sensitivity-panel summary").click()
    u_start, u_end = _utf16_span(M3_UNICODE_TEXT, "hơi nóng")
    _select_raw_text_utf16(detail, u_start, u_end)
    expect(detail.locator(".sensitivity-variant-preview")).to_have_text(
        M3_UNICODE_VARIANT
    )
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # 4. NFD combining mark guard ("Ca" cannot split "Ca\u0301n")
    page.locator(".item-table tbody tr", has_text="hỗ trợ nhiệt tình.").locator(
        "button"
    ).first.click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label(
        "Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True
    ).fill("Ca")
    expect(
        detail.get_by_text(
            "Đoạn khớp cắt ngang ký tự tổ hợp hoặc emoji nên không được chọn.",
            exact=True,
        )
    ).to_be_visible()
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # 5. Truncation >128 tokens: model_input_equal=True (MODEL_INPUT_UNCHANGED) & False (TOKEN_WINDOW_MAY_CHANGE)
    page.locator(".item-table tbody tr", has_text="Phần đầu cần thử").locator(
        "button"
    ).first.click()
    detail.locator("details.sensitivity-panel summary").click()
    q_trunc = detail.get_by_label(
        "Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True
    )
    q_trunc.fill(" phần cuối bị cắt.")
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)
    expect(detail.locator(".sensitivity-results")).to_contain_text(
        "Sau tiền xử lý và cắt ngắn, đầu vào model của hai văn bản giống nhau."
    )
    expect(detail.locator(".sensitivity-results")).to_contain_text(
        "Số token trước cắt: Gốc 139 (bị cắt) · Sau bỏ 135 (bị cắt)."
    )

    q_trunc.fill("Phần đầu cần thử ")
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)
    expect(detail.locator(".sensitivity-results")).to_contain_text(
        "Bỏ đoạn có thể đổi cách tách từ và đưa phần văn bản phía sau vào giới hạn 128 token."
    )
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # 6. Item with NO_PREDICTION runs sensitivity pair cleanly while Dự đoán AI gốc remains empty
    page.get_by_role("button", name=M3_NOPRED_TEXT, exact=True).click()
    expect(detail.locator(".prediction-section")).to_contain_text(
        "Chưa có dự đoán cho phiên bản này. Bạn có thể gán nhãn thủ công ở dưới."
    )
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label(
        "Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True
    ).fill("rất ổn")
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)
    expect(detail.locator(".sensitivity-results")).to_contain_text(
        "Phản hồi này chưa có dự đoán AI gốc trước đó; cặp gốc và biến thể được tính mới cho thử nghiệm và không thay thế phần Dự đoán AI gốc."
    )
    expect(detail.locator(".prediction-section")).to_contain_text(
        "Chưa có dự đoán cho phiên bản này. Bạn có thể gán nhãn thủ công ở dưới."
    )

    assert not page_errors
    assert not console_errors
    client.close()
    context.close()


def test_t08_races_cancel_5xx_retry_ttl_pair_invalid_and_locks(
    browser, controlled_server, missing_server
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "M3 Lifecycle & Races",
            "profile": "neu",
            "items": [
                {"text": M3_RACE_TEXT},
                {"text": M3_SECOND_ITEM_TEXT},
                {"text": M3_SLOW_TEXT},
                {"text": M3_PAIR_INVALID_TEXT},
            ],
        },
    ).json()
    run = client.post("/analysis-runs", json={"dataset_id": ds["id"]}).json()
    wait_for_run_terminal(client, ds["id"])

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")

    detail = page.locator("dialog.detail-panel")

    # --- 1. Rapid double-click on delayed POST -> strictly 1 POST, 0 self-cancels, job completes ---
    page.get_by_role("button", name=M3_RACE_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    q_input = detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True)
    q_input.fill("độ trễ")

    held_posts = []
    cancel_requests = []

    def track_cancel(req):
        if req.method == "POST" and req.url.endswith("/cancel"):
            cancel_requests.append(req.url)

    page.on("request", track_cancel)

    def hold_post(route):
        if route.request.method == "POST":
            held_posts.append(route)
        else:
            route.continue_()

    page.route("**/api/v1/items/*/sensitivity-experiments", hold_post)
    run_btn = detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)
    run_btn.evaluate("el => { el.click(); el.click(); }")
    deadline = time.monotonic() + 5
    while len(held_posts) == 0 and time.monotonic() < deadline:
        page.wait_for_timeout(25)
    page.wait_for_timeout(150)
    assert len(held_posts) == 1, f"Expected strictly 1 POST, got {len(held_posts)}"
    held_posts.pop(0).continue_()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)
    assert cancel_requests == []
    page.unroute("**/api/v1/items/*/sensitivity-experiments", hold_post)

    # --- 2a. Deferred POST + change selection while pending -> no stale attach + best-effort cancel ---
    cancel_requests.clear()
    held_posts.clear()
    page.route("**/api/v1/items/*/sensitivity-experiments", hold_post)
    q_input.fill("độ trễ")
    run_btn.click()
    deadline = time.monotonic() + 5
    while len(held_posts) == 0 and time.monotonic() < deadline:
        page.wait_for_timeout(25)
    q_input.fill("tác vụ")
    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/cancel")):
        held_posts.pop(0).continue_()
    page.wait_for_timeout(250)
    expect(detail.locator(".sensitivity-results")).to_have_count(0)
    assert len(cancel_requests) == 1
    page.unroute("**/api/v1/items/*/sensitivity-experiments", hold_post)

    # --- 2b. Deferred POST + close <details> panel while pending -> best-effort cancel & reset ---
    cancel_requests.clear()
    held_posts.clear()
    page.route("**/api/v1/items/*/sensitivity-experiments", hold_post)
    run_btn.click()
    deadline = time.monotonic() + 5
    while len(held_posts) == 0 and time.monotonic() < deadline:
        page.wait_for_timeout(25)
    detail.locator("details.sensitivity-panel summary").click()
    expect(detail.locator("details.sensitivity-panel")).not_to_have_attribute("open", "")
    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/cancel")):
        held_posts.pop(0).continue_()
    page.wait_for_timeout(200)
    assert len(cancel_requests) == 1
    detail.locator("details.sensitivity-panel summary").click()
    expect(q_input).to_have_value("")
    page.unroute("**/api/v1/items/*/sensitivity-experiments", hold_post)

    # --- 2c. Deferred POST + switch item while pending -> no leak to item 2 + best-effort cancel ---
    cancel_requests.clear()
    held_posts.clear()
    page.route("**/api/v1/items/*/sensitivity-experiments", hold_post)
    q_input.fill("độ trễ")
    run_btn.click()
    deadline = time.monotonic() + 5
    while len(held_posts) == 0 and time.monotonic() < deadline:
        page.wait_for_timeout(25)
    detail.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True).click()
    expect(detail).to_contain_text(M3_SECOND_ITEM_TEXT)
    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/cancel")):
        held_posts.pop(0).continue_()
    page.wait_for_timeout(250)
    assert len(cancel_requests) == 1
    detail.locator("details.sensitivity-panel summary").click()
    expect(detail.locator(".sensitivity-results")).to_have_count(0)
    page.unroute("**/api/v1/items/*/sensitivity-experiments", hold_post)
    page.remove_listener("request", track_cancel)

    # --- 3. 5xx POST retry retains exact same Idempotency-Key ---
    idempotency_keys = []

    def fail_first_post(route):
        idempotency_keys.append(route.request.headers.get("idempotency-key"))
        if len(idempotency_keys) == 1:
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"code": "TEMP_FAIL", "message": "Lỗi 500 giả lập khi tạo."}),
            )
        else:
            route.continue_()

    page.route("**/api/v1/items/*/sensitivity-experiments", fail_first_post)
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill("câu")
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.get_by_text("Lỗi 500 giả lập khi tạo.", exact=True)).to_be_visible()
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)
    assert len(idempotency_keys) == 2 and idempotency_keys[0] and idempotency_keys[0] == idempotency_keys[1]
    page.unroute("**/api/v1/items/*/sensitivity-experiments", fail_first_post)

    # --- 4. Editing source text draft locks creation until canceled ---
    detail.get_by_role("button", name="Sửa văn bản", exact=True).click()
    expect(
        detail.get_by_text(
            "Lưu hoặc hủy nháp văn bản nguồn trước khi thử nghiệm độ nhạy.", exact=True
        )
    ).to_be_visible()
    expect(detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)).to_be_disabled()
    detail.get_by_role("button", name="Hủy sửa", exact=True).click()
    expect(detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)).to_be_enabled()
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # --- 5. Active [SLOW_PAIR] job: cancel network failure (route.abort) + real cancel + polling 5xx backoff/stop ---
    page.get_by_role("button", name=M3_SLOW_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill("để kiểm hủy")

    def abort_cancel(route):
        route.abort()

    page.route("**/api/v1/jobs/*/cancel", abort_cancel)
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    cancel_btn = detail.get_by_role("button", name="Hủy thử nghiệm", exact=True)
    expect(cancel_btn).to_be_visible()
    cancel_btn.click()
    expect(
        detail.get_by_text(
            "Không thể kết nối dịch vụ local. Kiểm tra API đang chạy rồi thử lại.",
            exact=True,
        )
    ).to_be_visible()
    page.unroute("**/api/v1/jobs/*/cancel", abort_cancel)
    cancel_btn.click()
    expect(detail.get_by_text("Đã hủy thử nghiệm", exact=True)).to_be_visible(timeout=20000)

    # Polling 5xx backoff 1x then stops polling
    poll_get_count = []

    def fail_poll_500(route):
        if route.request.method == "GET":
            poll_get_count.append(route.request.url)
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"code": "POLL_500", "message": "Lỗi 500 khi poll thử nghiệm."}),
            )
        else:
            route.continue_()

    page.route("**/api/v1/sensitivity-experiments/*", fail_poll_500)
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/sensitivity-experiments" in r.url
    ) as created_resp:
        detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    slow_job_id = created_resp.value.json()["job_id"]
    expect(detail.get_by_text("Lỗi 500 khi poll thử nghiệm.", exact=True)).to_be_visible(
        timeout=15000
    )
    assert len(poll_get_count) == 2  # initial poll + 1 retry backoff
    page.wait_for_timeout(2200)
    assert len(poll_get_count) == 2  # stopped polling completely after error
    page.unroute("**/api/v1/sensitivity-experiments/*", fail_poll_500)
    client.post(f"/jobs/{slow_job_id}/cancel")
    deadline = time.monotonic() + 10
    while client.get(f"/jobs/{slow_job_id}").json()["status"] not in ("cancelled", "completed", "failed"):
        assert time.monotonic() < deadline
        time.sleep(0.1)
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # --- 5b. 409 EXPERIMENT_IN_PROGRESS + cancel error visible in role="alert" (P2 regression) ---
    items_now = client.get(f"/datasets/{ds['id']}/items").json()["items"]
    slow_item_now = next(i for i in items_now if i["text"] == M3_SLOW_TEXT)
    page.get_by_role("button", name=M3_SLOW_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill("để kiểm hủy")

    inprog_start, inprog_end = _utf16_span(slow_item_now["text"], "để kiểm hủy")
    inprog_resp = client.post(
        f"/items/{slow_item_now['id']}/sensitivity-experiments",
        json={
            "revision_id": slow_item_now["revision_id"],
            "expected_revision": slow_item_now["revision"],
            "text_sha256": hashlib.sha256(slow_item_now["text"].encode("utf-8")).hexdigest(),
            "run_id": None,
            "source_prediction_id": slow_item_now["prediction"]["id"],
            "selection": {
                "start_utf16": inprog_start,
                "end_utf16": inprog_end,
                "text": "để kiểm hủy",
            },
        },
        headers={"Idempotency-Key": "e2e-p2-inprogress-key"},
    )
    assert inprog_resp.status_code == 202, inprog_resp.text
    inprog_job_id = inprog_resp.json()["job_id"]

    page.route("**/api/v1/jobs/*/cancel", abort_cancel)
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(
        detail.get_by_text(
            "Phản hồi này đang có một thử nghiệm độ nhạy chưa kết thúc. Bạn có thể xem hoặc hủy thử nghiệm đang chạy.",
            exact=True,
        )
    ).to_be_visible()

    detail.get_by_role("button", name="Hủy thử nghiệm đang chạy", exact=True).click()
    cancel_err_alert = detail.locator(".sensitivity-body > p.error-text[role='alert']")
    expect(cancel_err_alert).to_be_visible()
    expect(cancel_err_alert).to_have_text(
        "Không thể kết nối dịch vụ local. Kiểm tra API đang chạy rồi thử lại."
    )
    page.unroute("**/api/v1/jobs/*/cancel", abort_cancel)

    detail.get_by_role("button", name="Xem thử nghiệm đang chạy", exact=True).click()
    expect(cancel_err_alert).to_have_count(0)
    expect(detail.locator(".sensitivity-result-area")).to_be_visible()
    client.post(f"/jobs/{inprog_job_id}/cancel")
    deadline = time.monotonic() + 10
    while client.get(f"/jobs/{inprog_job_id}").json()["status"] not in ("cancelled", "completed", "failed"):
        assert time.monotonic() < deadline
        time.sleep(0.1)
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # --- 6. 404 TTL expired after completion (SQLite expires_at cleanup + reconnect refetch, stops polling) ---
    page.get_by_role("button", name=M3_RACE_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill("tác vụ")
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)

    conn = sqlite3.connect(controlled_server.runtime / "workspace.sqlite3", timeout=10.0)
    try:
        conn.execute("UPDATE datasets SET expires_at = 1.0 WHERE temporary = 1")
        conn.commit()
    finally:
        conn.close()

    ttl_get_urls = []
    page.on(
        "request",
        lambda req: ttl_get_urls.append(req.url)
        if req.method == "GET" and "/sensitivity-experiments/" in req.url
        else None,
    )
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    with page.expect_response(
        lambda r: "/sensitivity-experiments/" in r.url and r.status == 404
    ):
        page.evaluate("window.dispatchEvent(new Event('online'))")
    expect(
        detail.get_by_text(
            "Kết quả tạm đã hết hạn hoặc không còn tồn tại; chạy lại nếu cần.",
            exact=True,
        )
    ).to_be_visible()
    assert len(ttl_get_urls) == 1  # No 404 retry
    page.wait_for_timeout(2200)
    assert len(ttl_get_urls) == 1  # Polling stays stopped
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # --- 7. [PAIR_INVALID] -> INVALID_PAIR_RESULT without partial table ---
    page.get_by_role("button", name=M3_PAIR_INVALID_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill("kết thúc")
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.get_by_text("Thử nghiệm không thể hoàn tất", exact=True)).to_be_visible(
        timeout=20000
    )
    expect(detail.get_by_text("Mã lỗi: INVALID_PAIR_RESULT", exact=True)).to_be_visible()
    expect(detail.get_by_role("button", name="Thử lại thử nghiệm", exact=True)).to_be_visible()
    assert detail.locator(".sensitivity-table").count() == 0
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    _assert_expected_console_only(
        page_errors,
        console_errors,
        allowed_substrings=("status of 409", "status of 500", "status of 404", "net::ERR_FAILED"),
    )
    context.close()
    client.close()

    # --- 8. Model unavailable (--without-model via missing_server) disables submit honestly ---
    missing_client = httpx.Client(base_url=missing_server.url + "/api/v1")
    ds_missing = missing_client.post(
        "/datasets",
        json={
            "name": "M3 No Model",
            "profile": "neu",
            "items": [{"text": "Phản hồi kiểm thử khi chưa có model."}],
        },
    ).json()
    m_ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    m_page = m_ctx.new_page()
    m_err, m_con = track_errors(m_page)
    m_page.goto(missing_server.url + f"/#/datasets/{ds_missing['id']}")
    m_page.get_by_role(
        "button", name="Phản hồi kiểm thử khi chưa có model.", exact=True
    ).click()
    m_detail = m_page.locator("dialog.detail-panel")
    m_detail.locator("details.sensitivity-panel summary").click()
    expect(
        m_detail.get_by_text(
            "Model cho hệ nhãn này chưa sẵn sàng nên chưa thể tạo thử nghiệm mới.",
            exact=True,
        )
    ).to_be_visible()
    expect(
        m_detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)
    ).to_be_disabled()
    assert not m_err
    assert not m_con
    m_ctx.close()
    missing_client.close()


def test_t08_out_of_band_source_context_changed_and_historical_stale(
    browser, controlled_server
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "M3 Out-of-Band Context & Stale",
            "profile": "neu",
            "items": [
                {"text": M3_SWITCH_TEXT},
                {"text": M3_RACE_TEXT},
            ],
        },
    ).json()
    items = client.get(f"/datasets/{ds['id']}/items").json()["items"]
    item_ctx = items[0]
    item_hist = items[1]

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")
    detail = page.locator("dialog.detail-panel")

    # 1. Out-of-band new run -> 409 SOURCE_CONTEXT_CHANGED -> Tải lại phản hồi keeps review draft & updates prediction
    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Nháp giữ qua SOURCE_CONTEXT_CHANGED"
    )
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "rất tốt"
    )

    run1 = client.post("/analysis-runs", json={"dataset_id": ds["id"]}).json()
    wait_for_run_terminal(client, ds["id"])

    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    reload_btn = detail.get_by_role("button", name="Tải lại phản hồi", exact=True)
    expect(reload_btn).to_be_visible()
    expect(detail.locator(".sensitivity-body")).to_contain_text(
        "nhãn rà soát đang nhập vẫn được giữ"
    )
    reload_btn.click()
    expect(detail.locator(".prediction-section")).to_contain_text("Tích cực")
    expect(
        detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)
    ).to_have_value("Nháp giữ qua SOURCE_CONTEXT_CHANGED")
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    page.reload()

    # 2. Historical run: completed experiment gets source_stale after out-of-band text edit,
    #    and pending view hits 409 REVISION_CONFLICT -> reload shows stale lock & retains text in disabled draft
    page.get_by_label("Lần phân tích", exact=True).select_option(run1["id"])
    page.get_by_role("button", name=M3_RACE_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "độ trễ"
    )
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)

    # Edit source item text out-of-band to revision 2
    edit_resp = client.patch(
        f"/items/{item_hist['id']}/text",
        json={"text": "M3: Văn bản đã chỉnh sửa ngoài luồng.", "expected_revision": 1},
    )
    assert edit_resp.status_code == 200

    # Refetch completed experiment via network reconnect event -> source_stale=true banner renders
    page.evaluate("window.dispatchEvent(new Event('offline'))")
    with page.expect_response(lambda r: "/sensitivity-experiments/" in r.url and r.ok):
        page.evaluate("window.dispatchEvent(new Event('online'))")
    expect(detail.locator(".sensitivity-results")).to_contain_text(
        "Văn bản nguồn đã thay đổi sang phiên bản mới sau khi chạy thử nghiệm. Kết quả bên dưới thuộc ảnh chụp văn bản tại thời điểm thử nghiệm."
    )

    # Reloading item under historical run after out-of-band edit hits stale lock cleanly
    # Let's also verify 409 REVISION_CONFLICT in historical view on item_ctx
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()
    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(
        "Nháp historical view"
    )
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "rất tốt"
    )
    edit_ctx = client.patch(
        f"/items/{item_ctx['id']}/text",
        json={"text": "M3: Văn bản switch đã chỉnh sửa ngoài luồng.", "expected_revision": 1},
    )
    assert edit_ctx.status_code == 200
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.get_by_role("button", name="Tải lại phản hồi", exact=True)).to_be_visible()
    detail.get_by_role("button", name="Tải lại phản hồi", exact=True).click()
    expect(detail).to_contain_text("Văn bản đã thay đổi sau lần phân tích này.")
    expect(detail).to_contain_text("Chuyển về văn bản hiện tại để thử")
    expect(
        detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)
    ).to_be_disabled()
    expect(
        detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)
    ).to_have_value("Nháp historical view")

    _assert_expected_console_only(
        page_errors, console_errors, allowed_substrings=("status of 409",)
    )
    context.close()
    client.close()


def test_t08_current_view_revision_conflict_reload_keeps_review_draft(
    browser, controlled_server
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "M3 Current Revision Conflict Draft",
            "profile": "neu",
            "items": [{"text": M3_SWITCH_TEXT}],
        },
    ).json()
    run = client.post("/analysis-runs", json={"dataset_id": ds["id"]}).json()
    assert run["id"]
    wait_for_run_terminal(client, ds["id"])
    item = client.get(f"/datasets/{ds['id']}/items").json()["items"][0]

    # Seed saved reviews on revision 1 so reload to revision 2 proves untouched task resets
    # cleanly while dirty draft is preserved and guarded by an input-revision conflict.
    pred = item["prediction"]
    for task in ("sentiment", "topic"):
        seeded = client.put(
            f"/items/{item['id']}/review",
            json={
                "task": task,
                "status": "confirmed",
                "label_id": pred[task]["label_id"],
                "source_prediction_id": pred["id"],
                "note": f"Nhãn đã lưu ở phiên bản 1 ({task})",
                "expected_revision": 1,
                "expected_review_revision": 0,
            },
        )
        assert seeded.status_code == 200, seeded.text

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
    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")

    page.get_by_role("button", name=M3_SWITCH_TEXT, exact=True).click()
    detail = page.locator("dialog.detail-panel")
    expect(detail).to_be_visible()

    draft_note = "Nháp rà soát quan trọng cần được giữ khi tải lại"
    # Seeded review starts at confirmed with source_prediction_id; making note dirty preserves confirmed draft.
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("confirmed")
    expect(detail.get_by_test_id("confirmed-source-sentiment")).to_contain_text(pred["id"])
    detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True).fill(draft_note)
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill(
        "rất tốt"
    )

    # Out-of-band text change creates revision 2 on current view
    edit_resp = client.patch(
        f"/items/{item['id']}/text",
        json={"text": "Phản hồi sau khi chỉnh sửa ngoài luồng.", "expected_revision": 1},
    )
    assert edit_resp.status_code == 200

    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    reload_btn = detail.get_by_role("button", name="Tải lại phản hồi", exact=True)
    expect(reload_btn).to_be_visible()
    expect(detail.locator(".sensitivity-body")).to_contain_text(
        "nhãn rà soát đang nhập vẫn được giữ"
    )
    reload_btn.click()

    expect(detail).to_contain_text("Phiên bản 2")
    expect(detail).to_contain_text("Phản hồi sau khi chỉnh sửa ngoài luồng.")
    # Confirmed sentiment draft (status + source + note) survives revision reload, while untouched topic resets to rev 2.
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("confirmed")
    expect(detail.get_by_test_id("confirmed-source-sentiment")).to_contain_text(pred["id"])
    expect(
        detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)
    ).to_have_value(draft_note)
    expect(detail.get_by_label("Trạng thái chủ đề", exact=True)).to_have_value("unreviewed")
    expect(detail.get_by_role("textbox", name="Ghi chú chủ đề", exact=True)).to_have_value("")
    expect(detail.get_by_test_id("review-topic")).to_contain_text("Chưa lưu nhãn duyệt")
    expect(detail.get_by_test_id("review-conflict-topic")).to_have_count(0)

    # Cross-input-revision conflict blocks direct save until reviewer resolves explicitly.
    sent_conflict = detail.get_by_test_id("review-conflict-sentiment")
    expect(sent_conflict).to_be_visible()
    expect(sent_conflict).to_have_attribute("role", "alert")
    expect(sent_conflict).to_contain_text("phiên bản 1")
    expect(sent_conflict).to_contain_text("phiên bản 2")
    expect(sent_conflict).to_contain_text(M3_SWITCH_TEXT)
    expect(sent_conflict).to_contain_text("Phản hồi sau khi chỉnh sửa ngoài luồng.")

    save_sent_btn = detail.get_by_role("button", name="Lưu cảm xúc", exact=True)
    save_next_btn = detail.get_by_role("button", name="Lưu và câu tiếp theo →", exact=True)
    expect(save_sent_btn).to_be_disabled()
    expect(save_next_btn).to_be_disabled()
    # Call the current React callbacks directly; disabled DOM events never reach them.
    invoke_bound_onclick(save_sent_btn, disabled=True)
    assert put_requests == [], "Save callback must not PUT while conflicted"
    invoke_bound_onclick(save_next_btn, disabled=True)
    page.wait_for_timeout(150)
    assert put_requests == []
    expect(detail).to_be_visible()
    expect(detail.locator("#detail-title")).to_have_text(f"Dòng {item['source_row']}")
    expect(sent_conflict).to_be_visible()
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("confirmed")
    expect(detail.get_by_test_id("confirmed-source-sentiment")).to_contain_text(pred["id"])
    expect(detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)).to_have_value(draft_note)
    assert client.get(f"/items/{item['id']}").json()["reviews"]["sentiment"] is None

    # Explicitly apply preserved draft onto revision 2: converts confirmed -> corrected, clears source_prediction_id.
    detail.get_by_role(
        "button", name="Áp nháp lên văn bản hiện tại: cảm xúc", exact=True
    ).click()
    expect(sent_conflict).to_have_count(0)
    expect(detail.get_by_label("Trạng thái cảm xúc", exact=True)).to_have_value("corrected")
    expect(detail.get_by_label("Nhãn cảm xúc đã sửa", exact=True)).to_have_value(
        str(pred["sentiment"]["label_id"])
    )
    expect(detail.get_by_test_id("confirmed-source-sentiment")).to_have_count(0)
    expect(
        detail.get_by_role("textbox", name="Ghi chú cảm xúc", exact=True)
    ).to_have_value(draft_note)
    expect(save_sent_btn).to_be_enabled()
    assert put_requests == []

    save_sent_btn.click()
    expect(detail.get_by_test_id("review-sentiment")).to_contain_text("Đã lưu · bản duyệt 1")
    saved_item = client.get(f"/items/{item['id']}").json()
    assert saved_item["revision"] == 2
    assert saved_item["reviews"]["sentiment"]["status"] == "corrected"
    assert saved_item["reviews"]["sentiment"]["label_id"] == pred["sentiment"]["label_id"]
    assert saved_item["reviews"]["sentiment"]["note"] == draft_note
    assert saved_item["reviews"]["sentiment"]["source_prediction_id"] is None
    assert saved_item["reviews"]["topic"] is None

    _assert_expected_console_only(
        page_errors, console_errors, allowed_substrings=("status of 409",)
    )
    context.close()
    client.close()


def test_t08_responsive_viewports_keyboard_only_and_mobile_screenshots(
    browser, controlled_server, screenshot_dir
):
    client = httpx.Client(base_url=controlled_server.url + "/api/v1")
    ds = client.post(
        "/datasets",
        json={
            "name": "M3 Responsive & Keyboard",
            "profile": "neu",
            "items": [{"text": M3_REPEAT_TEXT}, {"text": M3_SWITCH_TEXT}],
        },
    ).json()
    client.post("/analysis-runs", json={"dataset_id": ds["id"]})
    wait_for_run_terminal(client, ds["id"])

    # 1. Keyboard-only workflow at 1440x960 (Tab / Enter / Space / ArrowDown) + 1024x768 check
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page_errors, console_errors = track_errors(page)
    page.goto(controlled_server.url + f"/#/datasets/{ds['id']}")

    item_btn = page.get_by_role("button", name=M3_REPEAT_TEXT, exact=True)
    item_btn.focus()
    page.keyboard.press("Enter")
    detail = page.locator("dialog.detail-panel")
    expect(detail).to_be_visible()

    summary_el = detail.locator("details.sensitivity-panel summary")
    summary_el.focus()
    page.keyboard.press("Enter")
    expect(detail.locator("details.sensitivity-panel")).to_have_attribute("open", "")

    q_input = detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True)
    page.keyboard.press("Tab")
    expect(q_input).to_be_focused()
    page.keyboard.type("tốt")

    run_btn = detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True)
    run_btn.focus()
    page.keyboard.press("Enter")
    radios = detail.locator("fieldset.sensitivity-occurrences input[type='radio']")
    expect(radios.first).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(radios.nth(1)).to_be_checked()

    # Tab from selected radio group reaches Run button, Space triggers run
    for _ in range(4):
        page.keyboard.press("Tab")
        if run_btn.evaluate("el => el === document.activeElement"):
            break
    expect(run_btn).to_be_focused()
    page.keyboard.press(" ")
    results = detail.locator(".sensitivity-results")
    expect(results).to_be_visible(timeout=20000)

    expand_sent = results.get_by_role("button", name="Xem tất cả 4 nhãn", exact=True)
    expand_sent.focus()
    page.keyboard.press("Enter")
    expect(
        results.locator(".sensitivity-task-block").first.locator("tbody tr")
    ).to_have_count(4)

    assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert_no_horizontal_overflow(page, "1440x960 sensitivity keyboard")

    # 2. Laptop 1024x768 check
    page.set_viewport_size({"width": 1024, "height": 768})
    assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert_no_horizontal_overflow(page, "1024x768 sensitivity")
    detail.get_by_role("button", name="Đóng chi tiết", exact=True).click()

    # 3. Mobile 390x844 input + radio flow + screenshot
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name=M3_REPEAT_TEXT, exact=True).click()
    detail.locator("details.sensitivity-panel summary").click()
    detail.get_by_label("Nhập đoạn cần bỏ (đúng như văn bản gốc)", exact=True).fill("tốt")
    m_radios = detail.locator("fieldset.sensitivity-occurrences input[type='radio']")
    expect(m_radios).to_have_count(3)
    m_radios.nth(1).check()
    detail.get_by_role("button", name="Chạy thử khi bỏ đoạn", exact=True).click()
    expect(detail.locator(".sensitivity-results")).to_be_visible(timeout=20000)
    detail.locator(".sensitivity-results").scroll_into_view_if_needed()
    assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert_no_horizontal_overflow(page, "390x844 sensitivity")
    prepare_screenshot(page)
    _save_m3_screenshot(page, screenshot_dir, "m3-mobile-390-sensitivity.png")

    # 4. Mobile 320x568 overflow check + input/radio interaction + screenshot
    page.set_viewport_size({"width": 320, "height": 568})
    detail.locator(".sensitivity-results").get_by_role(
        "button", name="Xem tất cả 4 nhãn", exact=True
    ).click()
    detail.locator(".sensitivity-results").scroll_into_view_if_needed()
    assert detail.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert_no_horizontal_overflow(page, "320x568 sensitivity")
    prepare_screenshot(page)
    _save_m3_screenshot(page, screenshot_dir, "m3-mobile-320-sensitivity.png")

    assert not page_errors
    assert not console_errors
    context.close()
    client.close()


def _serve_controlled():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve-controlled", action="store_true")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    os.environ["FEEDBACK_RUNTIME"] = args.runtime
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from services.api.main import create_app
    import uvicorn

    app = create_app(args.runtime, registry=ControlledE2ERegistry(), start_worker=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="error")


if __name__ == "__main__":
    _serve_controlled()
