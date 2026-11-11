import hashlib
import math
import unicodedata

import regex

from services.storage.db import DomainError

MAX_TEXT_CODEPOINTS = 5000
_GRAPHEME_RE = regex.compile(r'\X')


def utf16_offsets_to_cp(text: str) -> tuple[dict[int, int], int]:
    """Build exact mapping from UTF-16 code unit offsets to Python code point indices."""
    utf16_to_cp = {0: 0}
    utf16_pos = 0
    for cp_idx, ch in enumerate(text, 1):
        utf16_pos += 2 if ord(ch) > 0xFFFF else 1
        utf16_to_cp[utf16_pos] = cp_idx
    return utf16_to_cp, utf16_pos


def grapheme_boundaries(text: str) -> set[int]:
    """Return valid UAX #29 extended grapheme cluster boundary code point indices."""
    boundaries = {0}
    for match in _GRAPHEME_RE.finditer(text):
        boundaries.add(match.end())
    return boundaries


def validate_and_build_variant(
    source_text: str,
    start_utf16: int,
    end_utf16: int,
    selected_text: str,
) -> dict:
    """Validate an exact UTF-16 selection against raw source_text and build variant_text."""
    if not isinstance(source_text, str):
        raise DomainError('INVALID_SELECTION', 'Văn bản nguồn không hợp lệ.', 422, {'reason': 'TEXT_MISMATCH'})
    if len(source_text) > MAX_TEXT_CODEPOINTS:
        raise DomainError('TEXT_TOO_LONG', 'Mỗi phản hồi tối đa 5.000 ký tự.', 422)

    utf16_to_cp, total_utf16 = utf16_offsets_to_cp(source_text)

    if type(start_utf16) is not int or type(end_utf16) is not int:
        raise DomainError('INVALID_SELECTION', 'Vị trí đoạn chọn không hợp lệ.', 422, {'reason': 'OUT_OF_RANGE'})
    if start_utf16 < 0 or end_utf16 < 0 or start_utf16 > total_utf16 or end_utf16 > total_utf16:
        raise DomainError('INVALID_SELECTION', 'Vị trí đoạn chọn nằm ngoài phạm vi văn bản.', 422, {'reason': 'OUT_OF_RANGE'})
    if start_utf16 >= end_utf16:
        raise DomainError('INVALID_SELECTION', 'Cần chọn một đoạn không rỗng.', 422, {'reason': 'EMPTY_SPAN'})
    if start_utf16 not in utf16_to_cp or end_utf16 not in utf16_to_cp:
        raise DomainError(
            'INVALID_SELECTION',
            'Vị trí đoạn chọn cắt giữa ký tự Unicode.',
            422,
            {'reason': 'SURROGATE_BOUNDARY'},
        )

    start_cp = utf16_to_cp[start_utf16]
    end_cp = utf16_to_cp[end_utf16]
    if not isinstance(selected_text, str) or source_text[start_cp:end_cp] != selected_text:
        raise DomainError(
            'INVALID_SELECTION',
            'Đoạn đã chọn không khớp chính xác với văn bản gốc.',
            422,
            {'reason': 'TEXT_MISMATCH'},
        )

    boundaries = grapheme_boundaries(source_text)
    if start_cp not in boundaries or end_cp not in boundaries:
        raise DomainError(
            'INVALID_SELECTION',
            'Không thể cắt giữa ký tự tổ hợp, emoji hoặc cặp xuống dòng.',
            422,
            {'reason': 'GRAPHEME_BOUNDARY'},
        )

    if not selected_text or not selected_text.strip():
        raise DomainError(
            'INVALID_SELECTION',
            'Đoạn chọn không được chỉ chứa khoảng trắng.',
            422,
            {'reason': 'WHITESPACE_ONLY'},
        )

    variant_text = source_text[:start_cp] + source_text[end_cp:]
    if len(variant_text) > MAX_TEXT_CODEPOINTS:
        raise DomainError('TEXT_TOO_LONG', 'Văn bản sau khi bỏ đoạn vượt quá 5.000 ký tự.', 422)
    if not variant_text or not variant_text.strip():
        raise DomainError(
            'EMPTY_VARIANT',
            'Không thể bỏ toàn bộ nội dung hoặc chỉ để lại khoảng trắng.',
            422,
            {'reason': 'EMPTY_VARIANT'},
        )
    if not any(unicodedata.category(ch)[0] in ('L', 'N') for ch in variant_text):
        raise DomainError(
            'NON_LEXICAL_VARIANT',
            'Phần văn bản còn lại cần giữ ít nhất một chữ cái hoặc chữ số.',
            422,
            {'reason': 'NON_LEXICAL_VARIANT'},
        )

    return {
        'start_utf16': start_utf16,
        'end_utf16': end_utf16,
        'start_cp': start_cp,
        'end_cp': end_cp,
        'baseline_text': source_text,
        'variant_text': variant_text,
        'baseline_sha256': hashlib.sha256(source_text.encode('utf-8')).hexdigest(),
        'variant_sha256': hashlib.sha256(variant_text.encode('utf-8')).hexdigest(),
    }


def _valid_pair_prediction(
    prediction: dict | None,
    execution: dict,
    profile: dict,
    expected_item: dict | None = None,
) -> bool:
    if not isinstance(prediction, dict):
        return False
    if expected_item is not None:
        if 'id' in expected_item and 'item_id' in prediction and prediction.get('item_id') != expected_item['id']:
            return False
        if 'revision_id' in expected_item and 'revision_id' in prediction and prediction.get('revision_id') != expected_item['revision_id']:
            return False
    if any(prediction.get(k) != execution.get(k) for k in ('schema_id', 'model_id', 'model_version')):
        return False
    if type(prediction.get('truncated')) is not bool:
        return False
    if 'token_count_before_truncation' in prediction:
        tc = prediction.get('token_count_before_truncation')
        if type(tc) is not int or tc < 0:
            return False
    if 'warnings' in prediction:
        w = prediction.get('warnings')
        if not isinstance(w, list) or any(not isinstance(entry, str) for entry in w):
            return False
    if 'duration_ms' in prediction:
        dur = prediction.get('duration_ms')
        if type(dur) not in (int, float) or not math.isfinite(dur) or dur < 0:
            return False
    for task in ('sentiment', 'topic'):
        labels = profile.get(task)
        task_pred = prediction.get(task)
        if not isinstance(labels, list) or not isinstance(task_pred, dict):
            return False
        valid_ids = {entry['id'] for entry in labels if isinstance(entry, dict) and type(entry.get('id')) is int}
        if type(task_pred.get('label_id')) is not int or task_pred['label_id'] not in valid_ids:
            return False
        scores = task_pred.get('scores')
        if not isinstance(scores, list) or len(scores) != len(labels):
            return False
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0.0 or v > 1.0 for v in scores):
            return False
        if abs(sum(float(v) for v in scores) - 1.0) > 0.001:
            return False
    return True


def build_sensitivity_result(
    baseline_item: dict,
    variant_item: dict,
    profile: dict,
    context: dict,
) -> dict | None:
    """Build same-label score comparison and honest diagnostics when pair results are complete."""
    attempt = context.get('attempt') if isinstance(context, dict) else None
    model_input_equal = attempt.get('model_input_equal') if isinstance(attempt, dict) else None
    if type(model_input_equal) is not bool:
        return None

    execution = context.get('execution') if isinstance(context, dict) else None
    if not isinstance(execution, dict):
        return None

    baseline_pred = baseline_item.get('prediction') if isinstance(baseline_item, dict) else None
    variant_pred = variant_item.get('prediction') if isinstance(variant_item, dict) else None
    if not _valid_pair_prediction(baseline_pred, execution, profile, expected_item=baseline_item):
        return None
    if not _valid_pair_prediction(variant_pred, execution, profile, expected_item=variant_item):
        return None

    comparison = {}
    for task in ('sentiment', 'topic'):
        b_task = baseline_pred[task]
        v_task = variant_pred[task]
        b_scores = b_task['scores']
        v_scores = v_task['scores']
        score_rows = []
        for idx, entry in enumerate(profile[task]):
            before = float(b_scores[idx])
            after = float(v_scores[idx])
            score_rows.append({
                'label_id': entry['id'],
                'before': before,
                'after': after,
                'delta': after - before,
            })
        comparison[task] = {
            'baseline_label_id': b_task['label_id'],
            'variant_label_id': v_task['label_id'],
            'scores': score_rows,
        }

    b_trunc = baseline_pred['truncated'] is True
    v_trunc = variant_pred['truncated'] is True
    warnings = ['SENSITIVITY_NOT_CAUSAL']
    if b_trunc:
        warnings.append('INPUT_TRUNCATED_BASELINE')
    if v_trunc:
        warnings.append('INPUT_TRUNCATED_VARIANT')
    if model_input_equal:
        warnings.append('MODEL_INPUT_UNCHANGED')
    elif b_trunc or v_trunc:
        warnings.append('TOKEN_WINDOW_MAY_CHANGE')

    return {
        'baseline': {
            'text': baseline_item['text'],
            'prediction': baseline_pred,
        },
        'variant': {
            'text': variant_item['text'],
            'prediction': variant_pred,
        },
        'model_input_equal': model_input_equal,
        'comparison': comparison,
        'warnings': warnings,
    }
