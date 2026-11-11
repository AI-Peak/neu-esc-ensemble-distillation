import copy
import hashlib
import json
import math
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = json.loads((ROOT / 'services/profiles.json').read_text(encoding='utf-8-sig'))
DEFAULT_POLICY_PATH = ROOT / 'services/review_policy.json'
EXPECTED_SCHEMA_IDS = {profile['schema_id'] for profile in PROFILES}
TASKS = ('sentiment', 'topic')
SCORE_SUM_TOLERANCE = 0.001

_DEFAULT_POLICY_LOCK = threading.Lock()
_DEFAULT_POLICY = None


def _reject_nonfinite_constant(token):
    raise ValueError(f'Invalid JSON constant in review policy: {token!r}')


def _validate_threshold(value, field_name):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise ValueError(f'Invalid threshold {field_name}: {value!r}')
    return float(value)


def _validate_policy_payload(data, policy_hash):
    if not isinstance(data, dict):
        raise ValueError('Review policy must be a JSON object.')
    expected_top_keys = {'id', 'experimental', 'schemas'}
    if set(data.keys()) != expected_top_keys:
        raise ValueError(f'Review policy must contain exact keys {sorted(expected_top_keys)}.')

    policy_id = data['id']
    if not isinstance(policy_id, str) or not policy_id.strip():
        raise ValueError('Review policy id must be a non-empty string.')

    experimental = data['experimental']
    if type(experimental) is not bool:
        raise ValueError('Review policy experimental flag must be a strict boolean.')

    schemas = data['schemas']
    if not isinstance(schemas, dict) or set(schemas.keys()) != EXPECTED_SCHEMA_IDS:
        raise ValueError(f'Review policy schemas must match profile schema IDs {sorted(EXPECTED_SCHEMA_IDS)}.')

    validated_schemas = {}
    for schema_id, schema_cfg in schemas.items():
        if not isinstance(schema_cfg, dict) or set(schema_cfg.keys()) != set(TASKS):
            raise ValueError(f'Schema {schema_id!r} must contain exact task keys {list(TASKS)}.')
        validated_tasks = {}
        for task in TASKS:
            task_cfg = schema_cfg[task]
            if not isinstance(task_cfg, dict) or set(task_cfg.keys()) != {'top1_min', 'margin_min'}:
                raise ValueError(f'Thresholds for {schema_id}.{task} must contain exact keys top1_min and margin_min.')
            validated_tasks[task] = {
                'top1_min': _validate_threshold(task_cfg['top1_min'], f'{schema_id}.{task}.top1_min'),
                'margin_min': _validate_threshold(task_cfg['margin_min'], f'{schema_id}.{task}.margin_min'),
            }
        validated_schemas[schema_id] = validated_tasks

    return {
        'id': policy_id,
        'hash': policy_hash,
        'experimental': experimental,
        'schemas': validated_schemas,
    }


def _read_policy_file(path):
    policy_path = Path(path)
    raw_bytes = policy_path.read_bytes()
    policy_hash = hashlib.sha256(raw_bytes).hexdigest()
    try:
        text = raw_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError(f'Review policy must be valid UTF-8: {policy_path}') from exc
    data = json.loads(text, parse_constant=_reject_nonfinite_constant)
    return _validate_policy_payload(data, policy_hash)


def load_policy(path=None):
    global _DEFAULT_POLICY
    if path is not None:
        return _read_policy_file(path)
    if _DEFAULT_POLICY is None:
        with _DEFAULT_POLICY_LOCK:
            if _DEFAULT_POLICY is None:
                _DEFAULT_POLICY = _read_policy_file(DEFAULT_POLICY_PATH)
    return copy.deepcopy(_DEFAULT_POLICY)


def resolve_policy_metadata(schema_id, policy=None):
    resolved_policy = load_policy() if policy is None else policy
    schemas = resolved_policy.get('schemas') if isinstance(resolved_policy, dict) else None
    if not isinstance(schemas, dict) or schema_id not in schemas:
        raise ValueError(f'Policy does not define thresholds for schema {schema_id!r}.')
    schema_cfg = schemas[schema_id]
    return {
        'id': resolved_policy['id'],
        'hash': resolved_policy['hash'],
        'experimental': resolved_policy['experimental'],
        'schema_id': schema_id,
        'sentiment': dict(schema_cfg['sentiment']),
        'topic': dict(schema_cfg['topic']),
    }


def review_relation(review, prediction_id):
    if not review or review.get('status') == 'unreviewed':
        return 'unreviewed'
    source_prediction_id = review.get('source_prediction_id')
    if source_prediction_id is None:
        return 'manual'
    if prediction_id is not None and source_prediction_id == prediction_id:
        return 'current_prediction'
    return 'other_prediction'


def _unavailable_signal(reason, relation):
    return {
        'state': 'unavailable',
        'top1_label_id': None,
        'top2_label_id': None,
        'top1': None,
        'top2': None,
        'margin': None,
        'reasons': [reason],
        'review_relation': relation,
    }


def evaluate_task_signal(prediction, review, profile, task, thresholds):
    prediction_id = prediction.get('id') if isinstance(prediction, dict) else None
    relation = review_relation(review, prediction_id)
    if prediction is None:
        return _unavailable_signal('NO_PREDICTION', relation)
    if not isinstance(prediction, dict) or prediction.get('schema_id') != profile.get('schema_id'):
        return _unavailable_signal('INVALID_SCORES', relation)

    labels = profile.get(task)
    if not isinstance(labels, list) or len(labels) < 2:
        return _unavailable_signal('INVALID_SCORES', relation)
    valid_ids = {entry['id'] for entry in labels if isinstance(entry, dict) and type(entry.get('id')) is int}

    task_obj = prediction.get(task)
    if not isinstance(task_obj, dict):
        return _unavailable_signal('INVALID_SCORES', relation)
    label_id = task_obj.get('label_id')
    if type(label_id) is not int or label_id not in valid_ids:
        return _unavailable_signal('INVALID_SCORES', relation)

    scores = task_obj.get('scores')
    if not isinstance(scores, list) or len(scores) != len(labels):
        return _unavailable_signal('INVALID_SCORES', relation)
    for score in scores:
        if type(score) not in (int, float) or not math.isfinite(score) or score < 0.0 or score > 1.0:
            return _unavailable_signal('INVALID_SCORES', relation)
    if abs(sum(float(score) for score in scores) - 1.0) > SCORE_SUM_TOLERANCE:
        return _unavailable_signal('INVALID_SCORES', relation)

    ranked = sorted(
        ((labels[idx]['id'], float(score)) for idx, score in enumerate(scores)),
        key=lambda pair: (-pair[1], pair[0]),
    )
    top1_label_id, top1 = ranked[0]
    top2_label_id, top2 = ranked[1]
    margin = top1 - top2

    reasons = []
    if top1 < float(thresholds['top1_min']):
        reasons.append('LOW_TOP1')
    if margin < float(thresholds['margin_min']):
        reasons.append('SMALL_MARGIN')

    return {
        'state': 'flagged' if reasons else 'clear',
        'top1_label_id': top1_label_id,
        'top2_label_id': top2_label_id,
        'top1': top1,
        'top2': top2,
        'margin': margin,
        'reasons': reasons,
        'review_relation': relation,
    }


def evaluate_item_signals(prediction, reviews, profile, policy=None):
    resolved_policy = load_policy() if policy is None else policy
    schema_id = profile['schema_id']
    policy_meta = resolve_policy_metadata(schema_id, resolved_policy)
    reviews_map = reviews or {}

    prediction_id = prediction.get('id') if isinstance(prediction, dict) else None
    sentiment_sig = evaluate_task_signal(
        prediction,
        reviews_map.get('sentiment'),
        profile,
        'sentiment',
        policy_meta['sentiment'],
    )
    topic_sig = evaluate_task_signal(
        prediction,
        reviews_map.get('topic'),
        profile,
        'topic',
        policy_meta['topic'],
    )

    truncated = None if prediction is None else (isinstance(prediction, dict) and prediction.get('truncated') is True)
    addressed_s = sentiment_sig['review_relation'] in ('current_prediction', 'manual')
    addressed_t = topic_sig['review_relation'] in ('current_prediction', 'manual')
    pending_signal_review = (
        (sentiment_sig['state'] == 'flagged' and not addressed_s)
        or (topic_sig['state'] == 'flagged' and not addressed_t)
        or (truncated is True and not (addressed_s and addressed_t))
    )

    return {
        'policy_id': policy_meta['id'],
        'policy_hash': policy_meta['hash'],
        'experimental': policy_meta['experimental'],
        'prediction_id': prediction_id,
        'sentiment': sentiment_sig,
        'topic': topic_sig,
        'truncated': truncated,
        'pending_signal_review': pending_signal_review,
    }
