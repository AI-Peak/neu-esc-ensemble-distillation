import hashlib
import json

import pytest

from services.sensitivity import grapheme_boundaries, utf16_offsets_to_cp, validate_and_build_variant
from services.storage.db import DomainError


def _utf16_span(text: str, needle: str, occurrence: int = 0) -> tuple[int, int]:
    start = -1
    pos = 0
    for _ in range(occurrence + 1):
        start = text.find(needle, pos)
        assert start != -1, f"needle {needle!r} occurrence {occurrence} not found in {text!r}"
        pos = start + 1
    end = start + len(needle)
    start_utf16 = len(text[:start].encode("utf-16-le")) // 2
    end_utf16 = len(text[:end].encode("utf-16-le")) // 2
    return start_utf16, end_utf16


def test_utf16_mapping_with_non_bmp_emoji_before_inside_and_after():
    # "🌍" is U+1F30D (1 code point, 2 UTF-16 code units).
    text_before = "A 🌍 rất tốt"
    s, e = _utf16_span(text_before, "rất tốt")
    assert (s, e) == (5, 12)
    built = validate_and_build_variant(text_before, s, e, "rất tốt")
    assert (built["start_cp"], built["end_cp"]) == (4, 11)
    assert built["baseline_text"] == text_before
    assert built["variant_text"] == "A 🌍 "
    assert built["baseline_sha256"] == hashlib.sha256(text_before.encode("utf-8")).hexdigest()
    assert built["variant_sha256"] == hashlib.sha256("A 🌍 ".encode("utf-8")).hexdigest()

    text_inside = "Đánh giá 🌍 rất tệ rồi"
    s2, e2 = _utf16_span(text_inside, "🌍 rất tệ")
    built2 = validate_and_build_variant(text_inside, s2, e2, "🌍 rất tệ")
    assert built2["variant_text"] == "Đánh giá  rồi"

    text_after = "Rất tệ 🌍 nhé"
    s3, e3 = _utf16_span(text_after, "Rất tệ")
    assert (s3, e3) == (0, 6)
    built3 = validate_and_build_variant(text_after, s3, e3, "Rất tệ")
    assert built3["variant_text"] == " 🌍 nhé"

    # Deleting the non-BMP emoji itself is valid as long as lexical text remains.
    text_emoji = "Tốt 🌍 lắm"
    s4, e4 = _utf16_span(text_emoji, "🌍")
    assert (s4, e4) == (4, 6)
    built4 = validate_and_build_variant(text_emoji, s4, e4, "🌍")
    assert built4["variant_text"] == "Tốt  lắm"


def test_rejects_utf16_surrogate_boundaries():
    text = "A 🌍 tốt"
    utf16_to_cp, total = utf16_offsets_to_cp(text)
    assert total == 8
    assert 3 not in utf16_to_cp

    with pytest.raises(DomainError) as exc_start:
        validate_and_build_variant(text, 3, 4, "")
    assert exc_start.value.code == "INVALID_SELECTION" and exc_start.value.status == 422
    assert exc_start.value.details == {"reason": "SURROGATE_BOUNDARY"}

    with pytest.raises(DomainError) as exc_end:
        validate_and_build_variant(text, 2, 3, "\ud83c")
    assert exc_end.value.code == "INVALID_SELECTION" and exc_end.value.status == 422
    assert exc_end.value.details == {"reason": "SURROGATE_BOUNDARY"}


def test_uax29_grapheme_boundaries_combining_zwj_skin_tone_flag_and_crlf():
    # 1. NFD Vietnamese combining mark: "a\u0301" is 1 grapheme cluster (2 code points).
    nfd = "ba\u0301o ca\u0301o tốt"
    bounds = grapheme_boundaries(nfd)
    assert 2 not in bounds  # Between 'a' and '\u0301'
    with pytest.raises(DomainError) as exc_nfd:
        validate_and_build_variant(nfd, 0, 2, "ba")
    assert exc_nfd.value.code == "INVALID_SELECTION" and exc_nfd.value.details == {"reason": "GRAPHEME_BOUNDARY"}
    valid_nfd = validate_and_build_variant(nfd, 0, 4, "ba\u0301o")
    assert valid_nfd["variant_text"] == " ca\u0301o tốt"

    # 2. ZWJ emoji sequence: woman scientist 👩🏽‍🔬 (U+1F469 U+1F3FD U+200D U+1F52C)
    zwj = "👩🏽‍🔬 làm việc tốt"
    zwj_cluster = "👩🏽‍🔬"
    for bad_cp in range(1, len(zwj_cluster)):
        bad_utf16 = len(zwj[:bad_cp].encode("utf-16-le")) // 2
        with pytest.raises(DomainError) as exc_zwj:
            validate_and_build_variant(zwj, 0, bad_utf16, zwj[:bad_cp])
        assert exc_zwj.value.code == "INVALID_SELECTION" and exc_zwj.value.details == {"reason": "GRAPHEME_BOUNDARY"}
    s_zwj, e_zwj = _utf16_span(zwj, zwj_cluster)
    assert validate_and_build_variant(zwj, s_zwj, e_zwj, zwj_cluster)["variant_text"] == " làm việc tốt"

    # 3. Skin tone modifier: 👍🏽 (U+1F44D U+1F3FD)
    skin = "👍🏽 rất ổn"
    with pytest.raises(DomainError) as exc_skin:
        validate_and_build_variant(skin, 0, 2, "👍")
    assert exc_skin.value.details == {"reason": "GRAPHEME_BOUNDARY"}
    s_skin, e_skin = _utf16_span(skin, "👍🏽")
    assert validate_and_build_variant(skin, s_skin, e_skin, "👍🏽")["variant_text"] == " rất ổn"

    # 4. Flag regional indicator pair: 🇻🇳 (U+1F1FB U+1F1F3)
    flag = "🇻🇳 tuyệt vời"
    with pytest.raises(DomainError) as exc_flag_surrogate:
        validate_and_build_variant(flag, 0, 1, "\ud83c")
    assert exc_flag_surrogate.value.details == {"reason": "SURROGATE_BOUNDARY"}
    with pytest.raises(DomainError) as exc_flag_half:
        validate_and_build_variant(flag, 0, 2, "🇻")
    assert exc_flag_half.value.details == {"reason": "GRAPHEME_BOUNDARY"}
    s_flag, e_flag = _utf16_span(flag, "🇻🇳")
    assert validate_and_build_variant(flag, s_flag, e_flag, "🇻🇳")["variant_text"] == " tuyệt vời"

    # 5. CRLF pair \r\n cannot be split.
    crlf = "Dòng một\r\nDòng hai"
    cr_idx = crlf.index("\r")
    with pytest.raises(DomainError) as exc_crlf:
        validate_and_build_variant(crlf, 0, cr_idx + 1, "Dòng một\r")
    assert exc_crlf.value.details == {"reason": "GRAPHEME_BOUNDARY"}
    with pytest.raises(DomainError) as exc_crlf_start:
        validate_and_build_variant(crlf, cr_idx + 1, len(crlf), "\nDòng hai")
    assert exc_crlf_start.value.details == {"reason": "GRAPHEME_BOUNDARY"}
    s_crlf, e_crlf = _utf16_span(crlf, "một\r\nDòng")
    assert validate_and_build_variant(crlf, s_crlf, e_crlf, "một\r\nDòng")["variant_text"] == "Dòng  hai"


def test_preserves_exact_whitespace_crlf_unicode_form_and_case():
    raw = "Dịch   vụ\t\r\nRất  Tốt!"
    s, e = _utf16_span(raw, "Rất  Tốt")
    built = validate_and_build_variant(raw, s, e, "Rất  Tốt")
    assert built["baseline_text"] == raw
    assert built["variant_text"] == "Dịch   vụ\t\r\n!"

    # Case sensitivity: no lowercase/casefold matching.
    with pytest.raises(DomainError) as exc_case:
        validate_and_build_variant(raw, s, e, "rất  tốt")
    assert exc_case.value.details == {"reason": "TEXT_MISMATCH"}

    # No NFC/NFD normalization: NFC selected_text must not match NFD source slice.
    nfd_source = "a\u0301 rất tốt"
    with pytest.raises(DomainError) as exc_norm:
        validate_and_build_variant(nfd_source, 0, 2, "\u00e1")
    assert exc_norm.value.details == {"reason": "TEXT_MISMATCH"}

    # Exact prefix and exact suffix deletions.
    first = validate_and_build_variant("Rất tốt luôn", 0, 4, "Rất ")
    assert first["variant_text"] == "tốt luôn"
    last = validate_and_build_variant("Rất tốt luôn", 7, 12, " luôn")
    assert last["variant_text"] == "Rất tốt"


def test_repeated_and_overlapping_occurrences_remove_single_span_only():
    repeated = "tốt không tốt nhưng tốt"
    s0, e0 = _utf16_span(repeated, "tốt", occurrence=0)
    s1, e1 = _utf16_span(repeated, "tốt", occurrence=1)
    s2, e2 = _utf16_span(repeated, "tốt", occurrence=2)
    assert validate_and_build_variant(repeated, s0, e0, "tốt")["variant_text"] == " không tốt nhưng tốt"
    assert validate_and_build_variant(repeated, s1, e1, "tốt")["variant_text"] == "tốt không  nhưng tốt"
    assert validate_and_build_variant(repeated, s2, e2, "tốt")["variant_text"] == "tốt không tốt nhưng "

    overlapping = "rất rất tệ rất"
    so, eo = _utf16_span(overlapping, "rất", occurrence=1)
    assert validate_and_build_variant(overlapping, so, eo, "rất")["variant_text"] == "rất  tệ rất"


@pytest.mark.parametrize(
    ("text", "start", "end", "selected", "expected_code", "expected_reason"),
    [
        ("Tốt lắm", -1, 3, "Tốt", "INVALID_SELECTION", "OUT_OF_RANGE"),
        ("Tốt lắm", 0, 99, "Tốt", "INVALID_SELECTION", "OUT_OF_RANGE"),
        ("Tốt lắm", 10, 11, "x", "INVALID_SELECTION", "OUT_OF_RANGE"),
        ("Tốt lắm", True, 3, "Tốt", "INVALID_SELECTION", "OUT_OF_RANGE"),
        ("Tốt lắm", 0, 1.5, "T", "INVALID_SELECTION", "OUT_OF_RANGE"),
        ("Tốt lắm", 2, 2, "", "INVALID_SELECTION", "EMPTY_SPAN"),
        ("Tốt lắm", 5, 2, "Tốt", "INVALID_SELECTION", "EMPTY_SPAN"),
        ("Tốt lắm", 0, 3, "Xấu", "INVALID_SELECTION", "TEXT_MISMATCH"),
        ("Tốt   lắm", 3, 6, "   ", "INVALID_SELECTION", "WHITESPACE_ONLY"),
        ("Tốt\t\r\nlắm", 3, 6, "\t\r\n", "INVALID_SELECTION", "WHITESPACE_ONLY"),
        ("Tốt", 0, 3, "Tốt", "EMPTY_VARIANT", "EMPTY_VARIANT"),
        ("  Tốt \r\n", 2, 5, "Tốt", "EMPTY_VARIANT", "EMPTY_VARIANT"),
        ("Tốt!!!", 0, 3, "Tốt", "NON_LEXICAL_VARIANT", "NON_LEXICAL_VARIANT"),
        ("Tốt 🌍...", 0, 3, "Tốt", "NON_LEXICAL_VARIANT", "NON_LEXICAL_VARIANT"),
    ],
)
def test_selection_rejection_matrix(text, start, end, selected, expected_code, expected_reason):
    with pytest.raises(DomainError) as exc:
        validate_and_build_variant(text, start, end, selected)
    assert exc.value.status == 422
    assert exc.value.code == expected_code
    assert exc.value.details == {"reason": expected_reason}


def test_lexical_numeric_variant_and_5000_codepoint_boundaries():
    # Unicode category 'N' (number) is accepted as lexical content.
    num_variant = validate_and_build_variant("Giá 100!", 0, 4, "Giá ")
    assert num_variant["variant_text"] == "100!"

    # Exactly 5000 BMP code points is accepted.
    max_text = "a" * 5000
    assert validate_and_build_variant(max_text, 0, 10, "a" * 10)["variant_text"] == "a" * 4990

    # Non-BMP emoji (>5000 UTF-16 units, <5000 code points) is accepted because limit is code points.
    emoji_text = ("🌍" * 2600) + " x abc"
    assert len(emoji_text) == 2606
    s, e = _utf16_span(emoji_text, "abc")
    assert s == 5203 and e == 5206
    assert validate_and_build_variant(emoji_text, s, e, "abc")["variant_text"] == ("🌍" * 2600) + " x "

    # 5001 code points fails cleanly with TEXT_TOO_LONG.
    with pytest.raises(DomainError) as exc_too_long:
        validate_and_build_variant("a" * 5001, 0, 1, "a")
    assert exc_too_long.value.status == 422 and exc_too_long.value.code == "TEXT_TOO_LONG"


def test_validation_errors_never_leak_raw_source_or_selected_text():
    secret = "BI_MAT_PHAN_HOI_RIENG_TU_98765"
    bad_cases = [
        (f"{secret} " + "a" * 5000, 0, 5, "aaaaa"),
        (f"ab {secret}", -1, 5, "ab"),
        (f"ab {secret}", 2, 2, ""),
        (f"🌍 {secret}", 1, 2, "\udc00"),
        (f"ab {secret}", 0, 2, secret),
        (f"ba\u0301 {secret}", 0, 2, "ba"),
        (f"   {secret}", 0, 3, "   "),
        (secret, 0, len(secret), secret),
        (f"{secret}!!!", 0, len(secret), secret),
    ]
    for source_text, start, end, selected in bad_cases:
        with pytest.raises(DomainError) as exc:
            validate_and_build_variant(source_text, start, end, selected)
        rendered = f"{exc.value.message} {json.dumps(exc.value.details)}"
        assert secret not in rendered


def test_build_sensitivity_result_rejects_half_pair_and_invalid_metadata():
    from services.sensitivity import build_sensitivity_result
    from services.storage.db import profile_for

    profile = profile_for("neu")
    execution = {
        "profile": "neu",
        "schema_id": "neu-v1",
        "model_id": "m",
        "model_version": "v1",
        "manifest_sha256": "a" * 64,
        "preprocessing_sha256": "b" * 64,
        "mode": "cpu-fp32-eval",
    }
    valid_b = {
        "id": "b1",
        "revision_id": "rb1",
        "text": "Dịch vụ rất tốt",
        "prediction": {
            "item_id": "b1",
            "revision_id": "rb1",
            "schema_id": "neu-v1",
            "model_id": "m",
            "model_version": "v1",
            "sentiment": {"label_id": 0, "scores": [0.7, 0.1, 0.1, 0.1]},
            "topic": {"label_id": 0, "scores": [0.55] + [0.05] * 9},
            "truncated": False,
            "token_count_before_truncation": 6,
            "warnings": [],
            "duration_ms": 1.0,
        },
    }
    valid_v = {
        "id": "v1",
        "revision_id": "rv1",
        "text": "Dịch vụ ",
        "prediction": None,
    }
    ctx = {"execution": execution, "attempt": {"error_code": None, "model_input_equal": False}}

    # Half-pair (variant missing prediction) must return None.
    assert build_sensitivity_result(valid_b, valid_v, profile, ctx) is None

    # Non-bool model_input_equal or mismatched item_id must return None.
    complete_v = {
        **valid_v,
        "prediction": {**valid_b["prediction"], "item_id": "v1", "revision_id": "rv1"},
    }
    assert build_sensitivity_result(valid_b, complete_v, profile, {"execution": execution, "attempt": {"model_input_equal": 1}}) is None
    bad_id_v = {**complete_v, "prediction": {**complete_v["prediction"], "item_id": "wrong"}}
    assert build_sensitivity_result(valid_b, bad_id_v, profile, ctx) is None
    assert build_sensitivity_result(valid_b, complete_v, profile, ctx) is not None
