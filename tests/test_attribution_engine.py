import pytest
import regex
import json
import os
import shutil
from transformers import AutoTokenizer
from pathlib import Path

from services.attribution import (
    align_and_group,
    generate_permutations,
    compute_shapley_from_coalition_map,
    utf16_offsets_to_cp,
    evaluate_coalition_outputs,
    target_value,
)

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture(scope="module")
def tokenizer(tmp_path_factory):
    # Read/copy tokenizer files only; no encoder, source model, or pointer is
    # loaded or mutated by these mapping mechanics tests.
    template = Path(os.environ.get('FEEDBACK_REAL_BUNDLE_TEMPLATE', ROOT / 'runtime/models'))
    profile_root = template / 'neu'
    pointer = profile_root / 'current.json'
    if not pointer.is_file():
        pytest.skip("Local PhoBERT tokenizer not found")
    version = json.loads(pointer.read_text(encoding='utf-8'))['version']
    source = (profile_root / 'versions' / version / 'tokenizer').resolve()
    assert source.is_relative_to(profile_root.resolve()) and source.is_dir()
    copied = tmp_path_factory.mktemp('attribution_tokenizer_only') / 'tokenizer'
    shutil.copytree(source, copied)
    return AutoTokenizer.from_pretrained(str(copied), use_fast=False, local_files_only=True)

def test_utf16_mapping():
    text = "Thân thiện 👍 và nhiệt tình"
    utf16_to_cp, cp_to_utf16, total_utf16 = utf16_offsets_to_cp(text)
    assert total_utf16 == len(text.encode("utf-16-le")) // 2
    # Verify roundtrip
    for cp_idx in range(len(text)):
        u16 = cp_to_utf16[cp_idx]
        assert utf16_to_cp[u16] == cp_idx

def test_align_and_group_basic(tokenizer):
    raw = "Nhân viên hỗ trợ thân thiện, nhưng cổng đăng ký học phần rất chậm và báo lỗi liên tục."
    res = align_and_group(raw, tokenizer)
    assert res["mapping_status"] == "exact"
    assert res["truncated"] is False
    groups = res["groups"]
    assert len(groups) > 0

    # Verify spans match raw text slices
    for g in groups:
        # Check slice
        slice_text = raw[g["start_utf16"]:g["end_utf16"]]
        assert slice_text == g["text"]

    # Verify non-overlapping partition
    all_tokens = []
    for g in groups:
        all_tokens.extend(g["token_indices"])
    assert all_tokens == list(range(1, len(res["full_input_ids"]) - 1))

def test_align_and_group_negation_intensifiers(tokenizer):
    raw = "Dịch vụ không tốt chút nào và giá quá đắt."
    res = align_and_group(raw, tokenizer)
    texts = [g["text"] for g in res["groups"]]
    assert "không tốt" in texts
    assert "quá đắt" in texts

def test_shapley_telescoping_additivity():
    # Synthetic coalition values with exact properties
    groups = [{"id": f"g_{i}", "text": f"word_{i}", "token_indices": [i+1]} for i in range(4)]
    perms, coalitions = generate_permutations(4, permutations_count=8, seed=42)

    # Define an arbitrary non-linear synthetic valuation function
    coalition_map = {}
    for c in coalitions:
        # e.g. base = 10, each item adds value plus interaction
        val = 10.0 + sum(i * 3.0 for i in c)
        if 0 in c and 1 in c:
            val += 5.0
        if 2 in c and 3 in c:
            val -= 4.0
        coalition_map[c] = val

    res = compute_shapley_from_coalition_map(groups, perms, coalition_map)
    # The telescoping sum of permutation Shapley must equal full - baseline exactly!
    baseline = res["baseline_value"]
    total = res["total_contribution"]
    target = res["target_output"]
    assert abs(baseline + total - target) < 1e-10
    assert res["additivity_residual"] < 1e-10


@pytest.mark.parametrize('raw', ['Ca\u0309m o\u031bn', 'Tốt 👍🏽', 'Tốt 👩\u200d💻'])
def test_mapping_consumes_full_words_and_never_splits_graphemes(tokenizer, raw):
    result = align_and_group(raw, tokenizer)
    _, cp_to_utf16, _ = utf16_offsets_to_cp(raw)
    boundaries = {0} | {cp_to_utf16[m.end()] for m in regex.finditer(r'\X', raw)}
    raw_utf16 = raw.encode('utf-16-le')
    slices = []
    for group in result['groups']:
        assert group['start_utf16'] in boundaries
        assert group['end_utf16'] in boundaries
        sliced = raw_utf16[2 * group['start_utf16']:2 * group['end_utf16']].decode('utf-16-le')
        assert sliced == group['text']
        slices.append(sliced)
    assert ''.join(slices).replace(' ', '') == raw.replace(' ', '')


@pytest.mark.parametrize('raw', [
    'Tốt tốt, tốt!', '  Tốt\t\t nhưng\r\n không tốt.  ', 'foo_bar rất tốt.',
    'Cảm ơn vì đã giúp đỡ.', 'Gia\u0301o vie\u0302n không nhiệt tình.',
    'https://example.test/path dài_liền_mạch.', '👍🏽👩\u200d💻!',
    'Sinh viên không hài lòng; dịch vụ chưa tốt.',
])
def test_raw_coverage_ids_whitespace_occurrences_and_punctuation(tokenizer, raw):
    import underthesea
    result = align_and_group(raw, tokenizer)
    segmented = underthesea.word_tokenize(raw, format='text')
    assert result['full_input_ids'] == tokenizer.encode(segmented, add_special_tokens=True)
    ids = [index for group in result['groups'] for index in group['token_indices']]
    assert ids == result['explained_token_indices']
    assert len(set(ids)) == len(ids)
    previous_end = 0
    u16_raw = raw.encode('utf-16-le')
    for group in result['groups']:
        assert group['start_utf16'] >= previous_end
        assert group['text'] == u16_raw[2 * group['start_utf16']:2 * group['end_utf16']].decode('utf-16-le')
        assert not u16_raw[2 * previous_end:2 * group['start_utf16']].decode('utf-16-le').strip()
        previous_end = group['end_utf16']
    assert not u16_raw[2 * previous_end:].decode('utf-16-le').strip()


def test_truncation_and_compaction_keep_all_tokens(tokenizer):
    raw = ' '.join(f'tốt {i}' for i in range(90))
    result = align_and_group(raw, tokenizer)
    assert result['truncated'] and result['mapping_status'] == 'unsupported'
    assert result['compacted'] and len(result['groups']) <= 24
    assert [i for g in result['groups'] for i in g['token_indices']] == result['explained_token_indices']


def test_unconsumed_or_mutated_characters_are_not_exact(tokenizer):
    class ChangedPreprocessor:
        spec = {'kind': 'underthesea_word_tokenize'}
        def transform(self, texts):
            return ['Cảm_ơn']
    with pytest.raises(ValueError):
        align_and_group('Cảm ơn nhưng không tốt.', tokenizer, ChangedPreprocessor())
    with pytest.raises(ValueError):
        align_and_group('Cảm xxx ơn', tokenizer, ChangedPreprocessor())


@pytest.mark.parametrize('profile_id', ['neu', 'uit'])
def test_every_target_uses_profile_keys_and_schema_order(profile_id):
    profiles = json.loads((ROOT / 'services/profiles.json').read_text(encoding='utf-8-sig'))
    profile = next(p for p in profiles if p['id'] == profile_id)
    n = len(profile['sentiment'])
    scores = [(i + 1) / sum(range(1, n + 1)) for i in range(n)]
    by_key = {label['key'].lower(): scores[i] for i, label in enumerate(profile['sentiment'])}
    assert target_value(scores, {'kind': 'polarity_margin'}, profile) == pytest.approx(100 * (by_key['positive'] - by_key['negative']))
    for label, score in zip(profile['sentiment'], scores):
        assert target_value(scores, {'kind': 'label_score', 'label_id': label['id']}, profile) == pytest.approx(100 * score)


def test_target_vector_order_is_schema_order_not_label_id():
    profile = {'sentiment': [{'id': 20, 'key': 'NeGaTiVe'}, {'id': 5, 'key': 'neutral'}, {'id': 99, 'key': 'POSITIVE'}]}
    assert target_value([.6, .3, .1], {'kind': 'polarity_margin'}, profile) == pytest.approx(-50)
    assert target_value([.6, .3, .1], {'kind': 'label_score', 'label_id': 99}, profile) == pytest.approx(10)
    for label_id in (-1, 0, True, 5.0):
        with pytest.raises(ValueError):
            target_value([.6, .3, .1], {'kind': 'label_score', 'label_id': label_id}, profile)


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), True, -1, 1.1])
def test_invalid_scores_never_become_zero(invalid):
    profile = {'sentiment': [{'id': 0, 'key': 'neutral'}, {'id': 1, 'key': 'positive'}]}
    with pytest.raises(ValueError):
        target_value([invalid, .5], {'kind': 'label_score', 'label_id': 0}, profile)
    groups = [{'id': 'g0'}]
    if invalid is True or not isinstance(invalid, (float, int)) or invalid != invalid or abs(invalid) == float('inf'):
        with pytest.raises(ValueError):
            compute_shapley_from_coalition_map(groups, [[0]], {frozenset(): 0., frozenset({0}): invalid})


def test_no_groups_or_partial_permutations_never_publish():
    with pytest.raises(ValueError):
        generate_permutations(0)
    with pytest.raises(ValueError):
        generate_permutations(1, 0)
    with pytest.raises(ValueError):
        compute_shapley_from_coalition_map([{}, {}], [[0]], {frozenset(): 0., frozenset({0, 1}): 1.})


def test_coalitions_use_tokenizer_mask_and_both_heads():
    import torch
    class Tokenizer:
        mask_token_id = 77
    seen = []
    class Model:
        def __call__(self, input_ids, attention_mask):
            seen.append((input_ids.tolist(), attention_mask.tolist()))
            return torch.zeros((len(input_ids), 3)), torch.ones((len(input_ids), 4))
    groups = [{'token_indices': [1]}, {'token_indices': [2]}]
    outputs = evaluate_coalition_outputs(Model(), [4, 21, 31, 5], groups, [frozenset(), frozenset({0, 1})], tokenizer=Tokenizer())
    assert seen == [([[4, 77, 77, 5], [4, 21, 31, 5]], [[1, 1, 1, 1], [1, 1, 1, 1]])]
    assert outputs[0]['sentiment'] == pytest.approx([1 / 3] * 3)
    assert outputs[1]['topic'] == pytest.approx([.25] * 4)
    class BadModel:
        def __call__(self, input_ids, attention_mask):
            return torch.full((len(input_ids), 3), float('nan')), torch.zeros((len(input_ids), 4))
    with pytest.raises(ValueError):
        evaluate_coalition_outputs(BadModel(), [4, 21, 31, 5], groups, [frozenset()], tokenizer=Tokenizer())


def test_prediction_provenance_is_bound_to_forward_not_a_later_identity_read(tmp_path, monkeypatch):
    import torch
    import services.inference.registry as registry_module
    registry = registry_module.ModelRegistry(tmp_path)
    directory = tmp_path / 'bundle'
    manifest = {'model_id': 'software-double', 'model_version': 'v1', 'schema_id': 'neu-v1',
                'preprocessing': {'kind': 'raw', 'use_fast': False, 'max_length': 128},
                'labels': {'sentiment': [{}, {}, {}, {}], 'topic': [{}] * 10}}
    fingerprint = [('manifest.json', 10, 20, False)]
    registry._validated[str(directory)] = (fingerprint, manifest)
    identity = {'profile': 'neu', 'schema_id': 'neu-v1', 'model_id': 'software-double',
                'model_version': 'v1', 'manifest_sha256': 'a' * 64,
                'preprocessing_sha256': 'b' * 64, 'mode': 'cpu-fp32-eval'}
    monkeypatch.setattr(registry, '_inspect', lambda profile: (directory, manifest))
    monkeypatch.setattr(registry, '_build_execution_identity', lambda *args: dict(identity))
    monkeypatch.setattr(registry_module, 'load_artifact', lambda *args: (object(), object()))
    logits = [(torch.zeros(4), torch.zeros(10))]
    monkeypatch.setattr(registry_module, 'run_logits', lambda *args: (logits, [3]))
    item = {'item_id': 'i', 'revision_id': 'r', 'text': 'Tốt'}
    prediction = registry.predict('neu', [item])[0]
    assert prediction['execution_identity'] == identity
    assert prediction['execution_identity'] is not identity

    def swapped_during_forward(*args):
        identity['manifest_sha256'] = 'c' * 64
        return logits, [3]
    monkeypatch.setattr(registry_module, 'run_logits', swapped_during_forward)
    with pytest.raises(registry_module.ModelIdentityChanged):
        registry.predict('neu', [item])
    assert registry._loaded is None
