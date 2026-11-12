"""Offline sampled permutation Shapley, with complete paths and exact raw spans.

Additivity of K=8 complete paths does not make the Shapley estimate exact and
does not prove a causal interpretation of masked, out-of-distribution inputs.
"""
from __future__ import annotations

import math
import random
from typing import Any
import unicodedata

import regex
MAX_INPUT_LENGTH = 128
MAX_GROUPS = 24
GROUPING_VERSION = 'raw_grapheme_compounds_v2'
METHOD_VERSION = '2.0'

INTENSIFIERS_NEGATIONS = {
    "không", "chẳng", "chưa", "rất", "quá", "cực_kỳ", "cực", "hơi", "khá",
    "hoàn_toàn", "tuyệt_đối", "vô_cùng", "hết_sức", "không_thể", "chưa_từng"
}

_GRAPHEME_RE = regex.compile(r"\X")


def utf16_offsets_to_cp(text: str) -> tuple[dict[int, int], dict[int, int], int]:
    """Build exact bidirectional mapping between UTF-16 code units and code points."""
    utf16_to_cp = {0: 0}
    cp_to_utf16 = {0: 0}
    utf16_pos = 0
    for cp_idx, ch in enumerate(text, 1):
        utf16_pos += 2 if ord(ch) > 0xFFFF else 1
        utf16_to_cp[utf16_pos] = cp_idx
        cp_to_utf16[cp_idx] = utf16_pos
    return utf16_to_cp, cp_to_utf16, utf16_pos


def align_and_group(raw_text: str, tokenizer, preprocessor=None, max_length=MAX_INPUT_LENGTH) -> dict[str, Any]:
    """Segment raw Vietnamese text, map to PhoBERT BPE tokens, and partition into groups.

    Guarantees:
    - Partition is non-overlapping and covers all content tokens.
    - Token indices match full_input_ids exactly.
    - Spans match raw_text characters exactly without cutting grapheme clusters.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ValueError("Input text must be non-empty string.")

    utf16_to_cp, cp_to_utf16, total_utf16 = utf16_offsets_to_cp(raw_text)

    # Never normalize model input just to make alignment easier.
    if preprocessor is None:
        from underthesea import word_tokenize
        segmented = word_tokenize(raw_text, format='text')
    else:
        if getattr(preprocessor, 'spec', {}).get('kind') not in (None, 'underthesea_word_tokenize'):
            raise ValueError('Chưa hỗ trợ ánh xạ cho pipeline của profile này.')
        processed = preprocessor.transform([raw_text])
        if not isinstance(processed, list) or len(processed) != 1:
            raise ValueError('Tiền xử lý không trả một văn bản hợp lệ.')
        segmented = processed[0]
    if not isinstance(segmented, str):
        raise ValueError('Tiền xử lý không trả văn bản hợp lệ.')
    words = segmented.split()
    if not words:
        raise ValueError("Text segmentation produced no tokens.")

    # Canonical decomposition is used only for matching. Every decomposed
    # code point retains its whole raw grapheme; fragments are merged below.
    units = []
    for match in _GRAPHEME_RE.finditer(raw_text):
        for char in unicodedata.normalize('NFD', match.group()):
            units.append((char, match.start(), match.end()))
    word_spans = []
    curr = 0
    for w in words:
        while curr < len(units) and units[curr][0].isspace():
            curr += 1
        start_unit = curr
        for char in unicodedata.normalize('NFD', w):
            if curr >= len(units):
                raise ValueError('Không ánh xạ được toàn bộ cụm từ về nguyên văn.')
            if char == '_' and units[curr][0].isspace():
                while curr < len(units) and units[curr][0].isspace():
                    curr += 1
            elif char == '_' and units[curr][0] != '_':
                # underthesea can join adjacent emoji fragments with an
                # inserted compound delimiter even without raw whitespace.
                # Match all real characters below; only this delimiter is empty.
                continue
            elif char == units[curr][0]:
                curr += 1
            else:
                raise ValueError('Tiền xử lý thay đổi ký tự; chưa ánh xạ chắc chắn về nguyên văn.')
        if curr == start_unit:
            raise ValueError('Cụm từ không chứa ký tự đã ánh xạ.')
        start, end = units[start_unit][1], units[curr - 1][2]
        word_spans.append((w, start, end, raw_text[start:end]))
    if any(not char.isspace() for char, _, _ in units[curr:]):
        raise ValueError('Tiền xử lý bỏ sót ký tự của nguyên văn.')

    # 3. Get BPE token IDs for each word and verify concatenation property
    word_token_ids = [tokenizer.encode(w, add_special_tokens=False) for w in words]
    if any(not ids for ids in word_token_ids):
        raise ValueError('Tokenizer bỏ sót một cụm từ.')
    full_encoded_content = tokenizer.encode(segmented, add_special_tokens=False)
    flat_word_ids = [idx for sub in word_token_ids for idx in sub]
    if flat_word_ids != full_encoded_content:
        raise ValueError("Token concatenation mismatch between per-word and full segmentation.")

    full_input_ids = list(tokenizer.encode(segmented, add_special_tokens=True))
    if hasattr(tokenizer, 'get_special_tokens_mask'):
        special_mask = tokenizer.get_special_tokens_mask(flat_word_ids, already_has_special_tokens=False)
        if len(special_mask) != len(full_input_ids) or any(v not in (0, 1) for v in special_mask):
            raise ValueError('Special token policy không hợp lệ.')
        positions = [i for i, special in enumerate(special_mask) if not special]
        if [full_input_ids[i] for i in positions] != flat_word_ids:
            raise ValueError('Special token policy không khớp full-input tokenization.')
    else:
        # Software doubles may expose only encode. Accept an unambiguous
        # contiguous content match; production tokenizers declare their policy.
        candidates = [s for s in range(len(full_input_ids) - len(flat_word_ids) + 1)
                      if full_input_ids[s:s + len(flat_word_ids)] == flat_word_ids]
        if len(candidates) != 1:
            raise ValueError('Không xác định được special token policy.')
        positions = list(range(candidates[0], candidates[0] + len(flat_word_ids)))
    if not positions:
        raise ValueError('Không có token nội dung để giải thích.')
    truncated = len(full_input_ids) > max_length

    # 4. Form groups (combine intensifier/negation with next word when valid)
    grouped_items = []
    i = 0
    n = len(words)
    token_offset = 0

    while i < n:
        w, s, e, raw_part = word_spans[i]
        t_ids = word_token_ids[i]

        if (unicodedata.normalize('NFC', w).lower() in INTENSIFIERS_NEGATIONS and i + 1 < n
                and any(unicodedata.category(c)[0] in ('L', 'N') for c in words[i + 1])):
            w2, s2, e2, raw_part2 = word_spans[i + 1]
            t_ids2 = word_token_ids[i + 1]
            group_text = raw_text[s:e2]
            group_token_indices = positions[token_offset:token_offset + len(t_ids) + len(t_ids2)]
            grouped_items.append({
                "id": f"g_{len(grouped_items)}",
                "text": group_text,
                "start_utf16": cp_to_utf16[s],
                "end_utf16": cp_to_utf16[e2],
                "token_indices": group_token_indices,
            })
            token_offset += len(t_ids) + len(t_ids2)
            i += 2
        else:
            group_token_indices = positions[token_offset:token_offset + len(t_ids)]
            grouped_items.append({
                "id": f"g_{len(grouped_items)}",
                "text": raw_part,
                "start_utf16": cp_to_utf16[s],
                "end_utf16": cp_to_utf16[e],
                "token_indices": group_token_indices,
            })
            token_offset += len(t_ids)
            i += 1

    # Emoji/ZWJ/combining fragments can be separate segmenter words. Their raw
    # spans share a grapheme; combine all fragments into one selectable group.
    merged = []
    for group in grouped_items:
        if merged and group['start_utf16'] < merged[-1]['end_utf16']:
            previous = merged[-1]
            previous['end_utf16'] = max(previous['end_utf16'], group['end_utf16'])
            previous['text'] = raw_text[utf16_to_cp[previous['start_utf16']]:utf16_to_cp[previous['end_utf16']]]
            previous['token_indices'].extend(group['token_indices'])
        else:
            merged.append(group)
    compacted = len(merged) > MAX_GROUPS
    if compacted:
        step = math.ceil(len(merged) / MAX_GROUPS)
        merged = [dict(start_utf16=chunk[0]['start_utf16'], end_utf16=chunk[-1]['end_utf16'],
                       text=raw_text[utf16_to_cp[chunk[0]['start_utf16']]:utf16_to_cp[chunk[-1]['end_utf16']]],
                       token_indices=[idx for part in chunk for idx in part['token_indices']])
                  for s in range(0, len(merged), step) for chunk in [merged[s:s + step]]]
    grouped_items = [dict(group, id=f'g_{idx}') for idx, group in enumerate(merged)]
    # Verify partition property: all content tokens covered, non-overlapping.
    covered_tokens = [idx for g in grouped_items for idx in g["token_indices"]]
    expected_tokens = positions
    if covered_tokens != expected_tokens:
        raise ValueError("Group tokens do not form an exact partition of content tokens.")

    return {
        "groups": grouped_items,
        "full_input_ids": full_input_ids,
        "truncated": truncated,
        "mapping_status": "exact" if not truncated else "unsupported",
        "total_utf16": total_utf16,
        'explained_token_indices': positions,
        'fixed_token_indices': [i for i in range(len(full_input_ids)) if i not in positions],
        'grouping_version': GROUPING_VERSION,
        'compacted': compacted,
    }


def generate_permutations(num_groups: int, permutations_count: int = 8, seed: int = 42) -> tuple[list[list[int]], list[frozenset[int]]]:
    """Generate K permutations and return list of permutations and ordered unique coalitions."""
    if type(num_groups) is not int or num_groups <= 0 or type(permutations_count) is not int or permutations_count <= 0:
        raise ValueError('Attribution cần ít nhất một nhóm và một hoán vị đầy đủ.')
    rng = random.Random(seed)
    all_indices = list(range(num_groups))
    permutations = []
    unique_coalitions: set[frozenset[int]] = set()

    # Always include baseline (empty) and full coalition
    unique_coalitions.add(frozenset())
    unique_coalitions.add(frozenset(all_indices))

    for _ in range(permutations_count):
        p = list(all_indices)
        rng.shuffle(p)
        permutations.append(p)
        current: set[int] = set()
        for idx in p:
            current.add(idx)
            unique_coalitions.add(frozenset(current))

    # Deterministic sorting of coalitions for reproducible batching
    sorted_coalitions = sorted(unique_coalitions, key=lambda c: (len(c), sorted(c)))
    return permutations, sorted_coalitions


def _scores_valid(scores):
    return (isinstance(scores, list) and len(scores) > 0
            and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in scores)
            and abs(math.fsum(scores) - 1) <= 1e-5)


def target_value(scores: list[float], target: dict, profile: dict) -> float:
    """Classifier vector order is the profile sentiment schema order, not IDs."""
    labels = profile.get('sentiment', [])
    if len(scores) != len(labels) or not _scores_valid(scores):
        raise ValueError('Điểm cảm xúc không khớp schema hoặc không hữu hạn.')
    ids = [row.get('id') for row in labels]
    if len(set(ids)) != len(ids) or any(type(idx) is not int for idx in ids):
        raise ValueError('Schema nhãn không hợp lệ.')
    by_id = dict(zip(ids, scores))
    if not isinstance(target, dict):
        raise ValueError('Target không hợp lệ.')
    if target.get('kind') == 'polarity_margin' and set(target) == {'kind'}:
        by_key = {row['key'].casefold(): row['id'] for row in labels}
        if not {'positive', 'negative'}.issubset(by_key):
            raise ValueError('Profile không có cặp nhãn Positive/Negative.')
        return 100.0 * (float(by_id[by_key['positive']]) - float(by_id[by_key['negative']]))
    if (target.get('kind') == 'label_score' and set(target) == {'kind', 'label_id'}
            and type(target.get('label_id')) is int and target['label_id'] in by_id):
        return 100.0 * float(by_id[target['label_id']])
    raise ValueError('Target không thuộc sentiment profile.')


def evaluate_coalition_outputs(
    model,
    base_input_ids: list[int],
    groups: list[dict],
    batch_coalitions: list[frozenset[int]],
    *, tokenizer,
) -> list[dict]:
    """Return both score vectors with the same full-input attention policy.

    Every coalition has the same length, so no padding is added. Masking changes
    content IDs only; it never changes sequence length or attention positions.
    """
    import torch
    mask_id = getattr(tokenizer, 'mask_token_id', None)
    if type(mask_id) is not int or mask_id < 0:
        raise ValueError('Tokenizer không hỗ trợ mask token.')
    if not groups or not base_input_ids:
        raise ValueError('Không có nhóm token để giải thích.')
    indices = [idx for group in groups for idx in group['token_indices']]
    if len(set(indices)) != len(indices) or any(type(idx) is not int or not 0 <= idx < len(base_input_ids) for idx in indices):
        raise ValueError('Partition token không hợp lệ.')
    if not batch_coalitions:
        return []
    input_tensor = []
    for c in batch_coalitions:
        if any(type(idx) is not int or not 0 <= idx < len(groups) for idx in c):
            raise ValueError('Coalition không hợp lệ.')
        inp = list(base_input_ids)
        for g_idx, g in enumerate(groups):
            if g_idx not in c:
                for t_pos in g["token_indices"]:
                    inp[t_pos] = mask_id
        input_tensor.append(inp)

    input_ids = torch.tensor(input_tensor, dtype=torch.long)
    mask = torch.ones_like(input_ids)

    with torch.inference_mode():
        logits = model(input_ids=input_ids, attention_mask=mask)
        if (not isinstance(logits, (list, tuple)) or len(logits) != 2
                or any(value.ndim != 2 or value.shape[0] != len(input_tensor) or value.shape[1] == 0
                       or not torch.isfinite(value).all() for value in logits)):
            raise ValueError('Model trả logits không hợp lệ.')
        probabilities = [value.float().softmax(-1).cpu().tolist() for value in logits]
    result = [{task: values[i] for task, values in zip(('sentiment', 'topic'), probabilities)}
              for i in range(len(input_tensor))]
    if any(not _scores_valid(row[task]) for row in result for task in ('sentiment', 'topic')):
        raise ValueError('Model trả điểm không hữu hạn.')
    return result


def evaluate_coalition_batch(model, base_input_ids, groups, batch_coalitions,
                             target_kind, target_label_id=None, *, tokenizer, profile):
    """Scalar compatibility wrapper; tokenizer and profile must be explicit."""
    target = {'kind': target_kind}
    if target_label_id is not None:
        target['label_id'] = target_label_id
    return [target_value(row['sentiment'], target, profile) for row in
            evaluate_coalition_outputs(model, base_input_ids, groups, batch_coalitions, tokenizer=tokenizer)]


def compute_shapley_from_coalition_map(
    groups: list[dict],
    permutations: list[list[int]],
    coalition_values: dict[frozenset[int], float],
) -> dict[str, Any]:
    """Compute sampled Shapley contributions from evaluated coalition values.

    Calculates float64 averages, ensures additivity invariant, and formats result.
    """
    num_groups = len(groups)
    if not groups or not permutations or any(sorted(p) != list(range(num_groups)) for p in permutations):
        raise ValueError('Cần nhóm và các hoán vị đầy đủ hợp lệ.')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in coalition_values.values()):
        raise ValueError('Coalition output không hữu hạn.')
    empty_c = frozenset()
    full_c = frozenset(range(num_groups))

    if empty_c not in coalition_values or full_c not in coalition_values:
        raise ValueError("Missing baseline or full coalition in evaluated values.")

    marginals = [[] for _ in groups]
    for p in permutations:
        current = empty_c
        prev_val = coalition_values[current]
        for g_idx in p:
            next_c = current | {g_idx}
            if next_c not in coalition_values:
                raise ValueError(f"Coalition {next_c} missing during Shapley calculation.")
            next_val = coalition_values[next_c]
            delta = next_val - prev_val
            marginals[g_idx].append(delta)
            current = next_c
            prev_val = next_val

    k = len(permutations)
    phi = [math.fsum(values) / k for values in marginals]

    baseline_val = float(coalition_values[empty_c])
    full_val = float(coalition_values[full_c])
    total_contribution = math.fsum(phi)
    residual = abs(baseline_val + total_contribution - full_val)
    if not math.isfinite(total_contribution) or residual > 1e-6:
        raise ValueError('Attribution không đạt ngưỡng cộng dồn.')

    # Attach contribution to each group
    result_groups = []
    for g_idx, g in enumerate(groups):
        entry = dict(g)
        entry["contribution"] = phi[g_idx]
        result_groups.append(entry)

    return {
        "groups": result_groups,
        "baseline_value": baseline_val,
        "total_contribution": total_contribution,
        "target_output": full_val,
        "additivity_residual": residual,
        "evaluated_coalitions": len(coalition_values),
    }
