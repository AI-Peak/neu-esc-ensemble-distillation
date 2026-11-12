"""Lightweight attribution invariants shared by API/storage/worker (no ML imports)."""
import hashlib
import json
import math

METHOD = {'id': 'permutation_shapley', 'version': '2.0',
          'grouping_version': 'raw_grapheme_compounds_v2', 'baseline_policy': 'all_groups_masked',
          'unit': 'percentage_points', 'seed': 42, 'requested_permutations': 8}
QUEUE_LIMIT = 10
CACHE_LIMIT = 100
TTL_SECONDS = 900
COMPUTE_SECONDS = 60


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def valid_identity(identity, profile, prediction):
    if not isinstance(identity, dict):
        return False
    return (identity.get('profile') == profile
            and all(identity.get(k) == prediction.get(k) for k in ('schema_id', 'model_id', 'model_version'))
            and identity.get('mode') == 'cpu-fp32-eval'
            and all(isinstance(identity.get(k), str) and len(identity[k]) == 64
                    and all(ch in '0123456789abcdef' for ch in identity[k])
                    for k in ('manifest_sha256', 'preprocessing_sha256')))


def source_snapshot(source):
    item, run = source['item'], source['run']
    prediction = item['prediction']
    return dict(source_job_id=source['job']['id'], source_prediction_id=prediction['id'],
                item_id=item['id'], revision_id=item['revision_id'], run_id=run['id'],
                text_hash=source['text_sha256'], profile_id=source['dataset']['profile'],
                schema_id=prediction['schema_id'], model_id=prediction['model_id'],
                model_version=prediction['model_version'], execution_identity=prediction['execution_identity'])


def check_vectors(outputs, profile):
    if not isinstance(outputs, dict):
        raise ValueError('Invalid coalition vectors')
    for head in ('sentiment', 'topic'):
        scores = outputs.get(head)
        if (not isinstance(scores, list) or len(scores) != len(profile[head])
                or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 or v > 1 for v in scores)
                or abs(math.fsum(scores) - 1) > 1e-5):
            raise ValueError('Invalid coalition head')


def check_parity(outputs, prediction, profile):
    check_vectors(outputs, profile)
    for head in ('sentiment', 'topic'):
        expected = prediction[head]['scores']
        if max(abs(a-b) for a, b in zip(outputs[head], expected)) > 1e-5:
            raise ValueError('Full input differs from source prediction')
        winner = max(range(len(outputs[head])), key=outputs[head].__getitem__)
        if profile[head][winner]['id'] != prediction[head]['label_id']:
            raise ValueError('Full input label differs from source prediction')
