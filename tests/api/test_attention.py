"""Contract tests for T01 backend topic attention aggregation and scope parities."""
import pytest
from fastapi.testclient import TestClient

from services.analytics import aggregate_attention, selected_labels
from services.api.main import create_app
from services.storage.db import profile_for
from services.worker import Worker


class ControlledRegistry:
    """Deterministic software-test double with explicit label mapping. Not a trained model."""

    __test__ = False

    def __init__(self, mapping=None, *, low_confidence_texts=None, fail=False, version='v1'):
        self.available = True
        self.fail = fail
        self.version = version
        self.mapping = dict(mapping or {})
        self.low_confidence_texts = set(low_confidence_texts or ())
        self.calls = []

    def status(self, profile):
        return {
            'available': self.available,
            'reason': None if self.available else 'Artifact missing',
            'model_id': f'test-double-{profile}',
            'model_version': self.version,
            'schema_id': profile_for(profile)['schema_id'],
        }

    def predict(self, profile, items):
        self.calls.append([i['item_id'] for i in items])
        if self.fail:
            raise RuntimeError('PRIVATE INPUT MUST NOT BE PERSISTED')
        prof = profile_for(profile)
        outputs = []
        for item in items:
            sent_id, topic_id = self.mapping.get(item['text'], (0, 0))
            low_conf = item['text'] in self.low_confidence_texts
            prediction = {
                'item_id': item['item_id'],
                'revision_id': item['revision_id'],
                'model_id': f'test-double-{profile}',
                'model_version': self.version,
                'schema_id': prof['schema_id'],
                'token_count_before_truncation': len(item['text'].split()) + 2,
                'truncated': False,
                'warnings': [],
                'duration_ms': 1.0,
            }
            for task, label_id in (('sentiment', sent_id), ('topic', topic_id)):
                count = len(prof[task])
                other = (0.2 if count == 4 else (0.25 if count == 3 else 0.05)) if low_conf else 0.02
                scores = [other] * count
                scores[label_id] = round(1.0 - other * (count - 1), 6)
                prediction[task] = {'label_id': label_id, 'scores': scores}
            outputs.append(prediction)
        return list(reversed(outputs))


@pytest.fixture
def env(tmp_path):
    registry = ControlledRegistry()
    app = create_app(tmp_path, registry)
    with TestClient(app) as client:
        yield client, app.state.store, registry, Worker(tmp_path, registry, batch_size=1)


def make_dataset(client, profile='neu', texts=None, **kwargs):
    items = [dict(text=t) for t in (texts or ['Mẫu một', 'Mẫu hai'])]
    response = client.post(
        '/api/v1/datasets',
        json=dict(name='Attention test', profile=profile, items=items, **kwargs),
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_run(client, dataset):
    response = client.post('/api/v1/analysis-runs', json=dict(dataset_id=dataset['id']))
    assert response.status_code == 202, response.text
    return response.json()


def drain(worker):
    for _ in range(510):
        if not worker.run_once():
            return
    raise AssertionError('Worker did not drain')


def fetch_items(client, dataset, **params):
    response = client.get(f"/api/v1/datasets/{dataset['id']}/items", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def fetch_summary(client, dataset, **params):
    response = client.get(f"/api/v1/datasets/{dataset['id']}/summary", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _row(item_id='i1', *, pred=None, reviews=None, reference=None, error=None):
    reviews = reviews or {}
    norm_reviews = {'sentiment': reviews.get('sentiment'), 'topic': reviews.get('topic')}
    prediction = None
    if pred is not None:
        s_id, t_id = pred
        prediction = {
            'id': f'pred-{item_id}',
            'sentiment': {'label_id': s_id, 'scores': []},
            'topic': {'label_id': t_id, 'scores': []},
        }
    effective = {}
    for task in ('sentiment', 'topic'):
        rev = norm_reviews[task]
        if rev is not None and rev.get('status') != 'unreviewed':
            effective[task] = rev.get('label_id')
        elif prediction is not None:
            effective[task] = prediction[task]['label_id']
        else:
            effective[task] = None
    return {
        'id': item_id,
        'prediction': prediction,
        'reviews': norm_reviews,
        'effective': effective,
        'reference': reference or {},
        'error': error,
    }


def _review(label_id, status='corrected'):
    return {'status': status, 'label_id': label_id}


def _assert_attention_invariants(agg, total_rows):
    assert agg['ranking_rule'] == 'negative_count_desc,eligible_count_desc,topic_id_asc'
    assert agg['small_sample_threshold'] == 5
    assert agg['filtered_count'] == total_rows
    assert (
        agg['filtered_count']
        == agg['eligible_count'] + agg['missing_topic_count'] + agg['missing_sentiment_with_topic_count']
    )
    assert sum(t['topic_count'] for t in agg['topics']) + agg['missing_topic_count'] == agg['filtered_count']
    assert sum(t['eligible_count'] for t in agg['topics']) == agg['eligible_count']
    assert sum(t['missing_sentiment_count'] for t in agg['topics']) == agg['missing_sentiment_with_topic_count']
    for topic in agg['topics']:
        assert topic['topic_count'] > 0
        assert topic['missing_sentiment_count'] == topic['topic_count'] - topic['eligible_count']
        assert topic['small_sample'] is (topic['eligible_count'] < 5)
        if topic['eligible_count'] == 0:
            assert topic['negative_rate'] is None
        else:
            assert topic['negative_rate'] == pytest.approx(topic['negative_count'] / topic['eligible_count'])


# ---------------------------------------------------------------------------
# 1. Pure helper unit tests: services.analytics
# ---------------------------------------------------------------------------


def test_selected_labels_effective_vs_ai_and_reference_isolation():
    # Mixed: manual sentiment + AI topic
    mixed = _row(
        'mixed',
        pred=(1, 4),
        reviews={'sentiment': _review(2, 'corrected'), 'topic': None},
        reference={'sentiment': {'label_id': 0, 'source': 'gold'}, 'topic': {'label_id': 3, 'source': 'gold'}},
    )
    assert selected_labels(mixed, 'effective') == {'sentiment': 2, 'topic': 4}
    assert selected_labels(mixed, 'ai') == {'sentiment': 1, 'topic': 4}

    # Unreviewed record falls back to AI, never reference
    unreviewed = _row(
        'unrev',
        pred=(1, 2),
        reviews={'sentiment': _review(None, 'unreviewed'), 'topic': _review(None, 'unreviewed')},
        reference={'sentiment': {'label_id': 2, 'source': 'gold'}, 'topic': {'label_id': 9, 'source': 'gold'}},
    )
    assert selected_labels(unreviewed, 'effective') == {'sentiment': 1, 'topic': 2}
    assert selected_labels(unreviewed, 'ai') == {'sentiment': 1, 'topic': 2}

    # No prediction and no reviews: reference must NEVER leak into effective or ai
    ref_only = _row(
        'ref_only',
        pred=None,
        reviews={},
        reference={'sentiment': {'label_id': 2, 'source': 'gold'}, 'topic': {'label_id': 4, 'source': 'gold'}},
    )
    assert selected_labels(ref_only, 'effective') == {'sentiment': None, 'topic': None}
    assert selected_labels(ref_only, 'ai') == {'sentiment': None, 'topic': None}

    # Model error + manual review on both tasks
    errored_reviewed = _row(
        'err_rev',
        pred=None,
        reviews={'sentiment': _review(2, 'corrected'), 'topic': _review(4, 'corrected')},
        reference={'sentiment': {'label_id': 1, 'source': 'gold'}, 'topic': {'label_id': 0, 'source': 'gold'}},
        error='Inference failed',
    )
    assert selected_labels(errored_reviewed, 'effective') == {'sentiment': 2, 'topic': 4}
    assert selected_labels(errored_reviewed, 'ai') == {'sentiment': None, 'topic': None}


@pytest.mark.parametrize(
    'profile_id,label_source,rows,expected',
    [
        # Empty dataset / filtered out to 0 rows (NEU)
        (
            'neu',
            'effective',
            [],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=0,
                eligible_count=0,
                missing_topic_count=0,
                missing_sentiment_with_topic_count=0,
                topics=[],
            ),
        ),
        # Empty dataset / filtered out to 0 rows (UIT)
        (
            'uit',
            'ai',
            [],
            dict(
                negative_label_id=0,
                toxic_label_id=None,
                filtered_count=0,
                eligible_count=0,
                missing_topic_count=0,
                missing_sentiment_with_topic_count=0,
                topics=[],
            ),
        ),
        # Missing topic (has sentiment) and missing both -> both go to missing_topic_count, no topic rows, no double count
        (
            'neu',
            'effective',
            [
                _row('r1', reviews={'sentiment': _review(2)}),
                _row('r2', reference={'sentiment': {'label_id': 2, 'source': 'g'}, 'topic': {'label_id': 4, 'source': 'g'}}),
            ],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=2,
                eligible_count=0,
                missing_topic_count=2,
                missing_sentiment_with_topic_count=0,
                topics=[],
            ),
        ),
        # Has topic, missing sentiment (eligible_count == 0 -> negative_rate is None, small_sample is True)
        # Mixed with one missing-topic row to verify partition invariant
        (
            'neu',
            'effective',
            [
                _row('r1', reviews={'topic': _review(4)}),
                _row('r2', reviews={'topic': _review(4)}),
                _row('r3', reviews={'sentiment': _review(2)}),
            ],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=3,
                eligible_count=0,
                missing_topic_count=1,
                missing_sentiment_with_topic_count=2,
                topics=[
                    dict(
                        topic_id=4,
                        topic_count=2,
                        eligible_count=0,
                        negative_count=0,
                        toxic_count=0,
                        negative_rate=None,
                        missing_sentiment_count=2,
                        small_sample=True,
                    )
                ],
            ),
        ),
        # Topic with mixed eligible + missing sentiment
        (
            'neu',
            'effective',
            [
                _row('r1', pred=(2, 4)),
                _row('r2', pred=(1, 4)),
                _row('r3', reviews={'topic': _review(4)}),
            ],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=3,
                eligible_count=2,
                missing_topic_count=0,
                missing_sentiment_with_topic_count=1,
                topics=[
                    dict(
                        topic_id=4,
                        topic_count=3,
                        eligible_count=2,
                        negative_count=1,
                        toxic_count=0,
                        negative_rate=0.5,
                        missing_sentiment_count=1,
                        small_sample=True,
                    )
                ],
            ),
        ),
        # Error row + 2 manual reviews: counted in effective, NOT in ai
        (
            'neu',
            'effective',
            [
                _row(
                    'err_manual',
                    pred=None,
                    reviews={'sentiment': _review(2), 'topic': _review(4)},
                    error='Inference failed',
                )
            ],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=1,
                eligible_count=1,
                missing_topic_count=0,
                missing_sentiment_with_topic_count=0,
                topics=[
                    dict(
                        topic_id=4,
                        topic_count=1,
                        eligible_count=1,
                        negative_count=1,
                        toxic_count=0,
                        negative_rate=1.0,
                        missing_sentiment_count=0,
                        small_sample=True,
                    )
                ],
            ),
        ),
        (
            'neu',
            'ai',
            [
                _row(
                    'err_manual',
                    pred=None,
                    reviews={'sentiment': _review(2), 'topic': _review(4)},
                    error='Inference failed',
                )
            ],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=1,
                eligible_count=0,
                missing_topic_count=1,
                missing_sentiment_with_topic_count=0,
                topics=[],
            ),
        ),
        # Mixed effective sources (manual sentiment + AI topic, confirmed both, AI-only)
        (
            'neu',
            'effective',
            [
                _row('m1', pred=(1, 4), reviews={'sentiment': _review(2, 'corrected')}),
                _row('m2', pred=(2, 4), reviews={'sentiment': _review(2, 'confirmed'), 'topic': _review(4, 'confirmed')}),
                _row('m3', pred=(1, 4)),
            ],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=3,
                eligible_count=3,
                missing_topic_count=0,
                missing_sentiment_with_topic_count=0,
                topics=[
                    dict(
                        topic_id=4,
                        topic_count=3,
                        eligible_count=3,
                        negative_count=2,
                        toxic_count=0,
                        negative_rate=pytest.approx(2 / 3),
                        missing_sentiment_count=0,
                        small_sample=True,
                    )
                ],
            ),
        ),
        (
            'neu',
            'ai',
            [
                _row('m1', pred=(1, 4), reviews={'sentiment': _review(2, 'corrected')}),
                _row('m2', pred=(2, 4), reviews={'sentiment': _review(2, 'confirmed'), 'topic': _review(4, 'confirmed')}),
                _row('m3', pred=(1, 4)),
            ],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=3,
                eligible_count=3,
                missing_topic_count=0,
                missing_sentiment_with_topic_count=0,
                topics=[
                    dict(
                        topic_id=4,
                        topic_count=3,
                        eligible_count=3,
                        negative_count=1,
                        toxic_count=0,
                        negative_rate=pytest.approx(1 / 3),
                        missing_sentiment_count=0,
                        small_sample=True,
                    )
                ],
            ),
        ),
        # NEU: Toxic (3) does NOT add to negative_count (2), still included in eligible_count; toxic_count tracked separately
        (
            'neu',
            'effective',
            [
                _row('n1', pred=(2, 4)),
                _row('n2', pred=(2, 4)),
                _row('t1', pred=(3, 4)),
                _row('t2', pred=(3, 4)),
                _row('p1', pred=(1, 4)),
                _row('tox_only', pred=(3, 9)),
            ],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=6,
                eligible_count=6,
                missing_topic_count=0,
                missing_sentiment_with_topic_count=0,
                topics=[
                    dict(
                        topic_id=4,
                        topic_count=5,
                        eligible_count=5,
                        negative_count=2,
                        toxic_count=2,
                        negative_rate=0.4,
                        missing_sentiment_count=0,
                        small_sample=False,
                    ),
                    dict(
                        topic_id=9,
                        topic_count=1,
                        eligible_count=1,
                        negative_count=0,
                        toxic_count=1,
                        negative_rate=0.0,
                        missing_sentiment_count=0,
                        small_sample=True,
                    ),
                ],
            ),
        ),
        # UIT: negative_label_id == 0, toxic_label_id is None, toxic_count is None
        (
            'uit',
            'effective',
            [
                _row('u1', pred=(0, 2)),
                _row('u2', pred=(0, 2)),
                _row('u3', pred=(2, 2)),
                _row('u4', pred=(1, 0)),
            ],
            dict(
                negative_label_id=0,
                toxic_label_id=None,
                filtered_count=4,
                eligible_count=4,
                missing_topic_count=0,
                missing_sentiment_with_topic_count=0,
                topics=[
                    dict(
                        topic_id=2,
                        topic_count=3,
                        eligible_count=3,
                        negative_count=2,
                        toxic_count=None,
                        negative_rate=pytest.approx(2 / 3),
                        missing_sentiment_count=0,
                        small_sample=True,
                    ),
                    dict(
                        topic_id=0,
                        topic_count=1,
                        eligible_count=1,
                        negative_count=0,
                        toxic_count=None,
                        negative_rate=0.0,
                        missing_sentiment_count=0,
                        small_sample=True,
                    ),
                ],
            ),
        ),
        # small_sample boundary: n=5 (False), n=4 (True), n=1 (True), n=0 (True), zero-negative still shown, empty topic omitted
        (
            'neu',
            'effective',
            [
                # Topic 4: n=5, neg=3 -> small_sample=False
                _row('b5_1', pred=(2, 4)),
                _row('b5_2', pred=(2, 4)),
                _row('b5_3', pred=(2, 4)),
                _row('b5_4', pred=(1, 4)),
                _row('b5_5', pred=(0, 4)),
                # Topic 2: n=4, neg=2 -> small_sample=True
                _row('b4_1', pred=(2, 2)),
                _row('b4_2', pred=(2, 2)),
                _row('b4_3', pred=(1, 2)),
                _row('b4_4', pred=(1, 2)),
                # Topic 5: n=1, neg=1 -> small_sample=True
                _row('b1_1', pred=(2, 5)),
                # Topic 7: n=1, neg=0 -> still appears, negative_rate=0.0, small_sample=True
                _row('b0n_1', pred=(1, 7)),
                # Topic 1: n=0, topic_count=1 -> still appears, negative_rate=None, small_sample=True
                _row('b0e_1', reviews={'topic': _review(1)}),
            ],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=12,
                eligible_count=11,
                missing_topic_count=0,
                missing_sentiment_with_topic_count=1,
                topics=[
                    dict(topic_id=4, topic_count=5, eligible_count=5, negative_count=3, toxic_count=0, negative_rate=0.6, missing_sentiment_count=0, small_sample=False),
                    dict(topic_id=2, topic_count=4, eligible_count=4, negative_count=2, toxic_count=0, negative_rate=0.5, missing_sentiment_count=0, small_sample=True),
                    dict(topic_id=5, topic_count=1, eligible_count=1, negative_count=1, toxic_count=0, negative_rate=1.0, missing_sentiment_count=0, small_sample=True),
                    dict(topic_id=7, topic_count=1, eligible_count=1, negative_count=0, toxic_count=0, negative_rate=0.0, missing_sentiment_count=0, small_sample=True),
                    dict(topic_id=1, topic_count=1, eligible_count=0, negative_count=0, toxic_count=0, negative_rate=None, missing_sentiment_count=1, small_sample=True),
                ],
            ),
        ),
        # Deterministic sort & tie-breaking: (-negative_count, -eligible_count, topic_id)
        # Note Topic 1 has 100% rate (2/2) but MUST rank below Topic 2 and Topic 5 (2/5)!
        (
            'neu',
            'effective',
            [
                # Topic 3: neg=0, elig=0 (topic_count=2)
                _row('s3_1', reviews={'topic': _review(3)}),
                _row('s3_2', reviews={'topic': _review(3)}),
                # Topic 9: neg=0, elig=3
                _row('s9_1', pred=(1, 9)),
                _row('s9_2', pred=(1, 9)),
                _row('s9_3', pred=(0, 9)),
                # Topic 1: neg=2, elig=2 (rate=1.0)
                _row('s1_1', pred=(2, 1)),
                _row('s1_2', pred=(2, 1)),
                # Topic 5: neg=2, elig=5 (rate=0.4)
                _row('s5_1', pred=(2, 5)),
                _row('s5_2', pred=(2, 5)),
                _row('s5_3', pred=(1, 5)),
                _row('s5_4', pred=(1, 5)),
                _row('s5_5', pred=(1, 5)),
                # Topic 2: neg=2, elig=5 (rate=0.4) -> ties with Topic 5, wins by topic_id_asc
                _row('s2_1', pred=(2, 2)),
                _row('s2_2', pred=(2, 2)),
                _row('s2_3', pred=(1, 2)),
                _row('s2_4', pred=(1, 2)),
                _row('s2_5', pred=(1, 2)),
                # Topic 8: neg=3, elig=4 -> highest negative_count
                _row('s8_1', pred=(2, 8)),
                _row('s8_2', pred=(2, 8)),
                _row('s8_3', pred=(2, 8)),
                _row('s8_4', pred=(1, 8)),
            ],
            dict(
                negative_label_id=2,
                toxic_label_id=3,
                filtered_count=21,
                eligible_count=19,
                missing_topic_count=0,
                missing_sentiment_with_topic_count=2,
                topics=[
                    dict(topic_id=8, topic_count=4, eligible_count=4, negative_count=3, toxic_count=0, negative_rate=0.75, missing_sentiment_count=0, small_sample=True),
                    dict(topic_id=2, topic_count=5, eligible_count=5, negative_count=2, toxic_count=0, negative_rate=0.4, missing_sentiment_count=0, small_sample=False),
                    dict(topic_id=5, topic_count=5, eligible_count=5, negative_count=2, toxic_count=0, negative_rate=0.4, missing_sentiment_count=0, small_sample=False),
                    dict(topic_id=1, topic_count=2, eligible_count=2, negative_count=2, toxic_count=0, negative_rate=1.0, missing_sentiment_count=0, small_sample=True),
                    dict(topic_id=9, topic_count=3, eligible_count=3, negative_count=0, toxic_count=0, negative_rate=0.0, missing_sentiment_count=0, small_sample=True),
                    dict(topic_id=3, topic_count=2, eligible_count=0, negative_count=0, toxic_count=0, negative_rate=None, missing_sentiment_count=2, small_sample=True),
                ],
            ),
        ),
    ],
)
def test_aggregate_attention_table_driven(profile_id, label_source, rows, expected):
    agg = aggregate_attention(rows, profile_for(profile_id), label_source)
    _assert_attention_invariants(agg, len(rows))
    for key in (
        'negative_label_id',
        'toxic_label_id',
        'filtered_count',
        'eligible_count',
        'missing_topic_count',
        'missing_sentiment_with_topic_count',
    ):
        assert agg[key] == expected[key]
    assert len(agg['topics']) == len(expected['topics'])
    for actual_topic, exp_topic in zip(agg['topics'], expected['topics']):
        for key, value in exp_topic.items():
            assert actual_topic[key] == value


# ---------------------------------------------------------------------------
# 2. API & Scope Integration tests via create_app + TestClient
# ---------------------------------------------------------------------------


def test_summary_and_items_scope_metadata_before_during_and_after_run(env):
    c, s, r, w = env
    # Preview CSV with reference labels to verify reference never feeds effective attention.
    csv_bytes = (
        'text,ref_sent,ref_topic\n'
        '"Cổng đăng ký lỗi liên tục",2,4\n'
        '"Thư viện hướng dẫn nhiệt tình",1,4\n'
    ).encode('utf-8-sig')
    preview = c.post('/api/v1/imports/preview', files={'file': ('demo.csv', csv_bytes, 'text/csv')}).json()
    d = c.post(
        '/api/v1/datasets',
        json=dict(
            name='Scope metadata',
            profile='neu',
            preview_id=preview['preview_id'],
            text_column='text',
            reference=dict(source='Tác giả', sentiment_column='ref_sent', topic_column='ref_topic'),
        ),
    ).json()

    # 1) Before any run
    summary0 = fetch_summary(c, d)
    items0 = fetch_items(c, d)
    for field in (
        'total',
        'processed',
        'reviewed',
        'partial_review',
        'unreviewed',
        'truncated',
        'errors',
        'sentiment',
        'topic',
        'cross',
        'denominator',
        'run_id',
        'label_source',
        'resolved_run_id',
        'revision_scope',
        'run_status',
        'attention',
    ):
        assert field in summary0
    assert summary0['run_id'] is None
    assert summary0['resolved_run_id'] is None
    assert summary0['revision_scope'] == 'current'
    assert summary0['run_status'] is None
    assert summary0['attention']['filtered_count'] == 2
    assert summary0['attention']['eligible_count'] == 0
    assert summary0['attention']['missing_topic_count'] == 2
    assert summary0['attention']['topics'] == []

    assert items0['run_id'] is None
    assert items0['resolved_run_id'] is None
    assert items0['revision_scope'] == 'current'
    assert items0['run_status'] is None

    # 2) Run queued (not yet processed)
    r.mapping = {
        'Cổng đăng ký lỗi liên tục': (2, 4),
        'Thư viện hướng dẫn nhiệt tình': (1, 4),
    }
    r1 = create_run(c, d)
    summary_q = fetch_summary(c, d)
    items_q = fetch_items(c, d)
    assert summary_q['run_id'] is None
    assert summary_q['resolved_run_id'] == r1['id']
    assert summary_q['revision_scope'] == 'current'
    assert summary_q['run_status'] == 'queued'
    assert items_q['run_id'] is None
    assert items_q['resolved_run_id'] == r1['id']
    assert items_q['revision_scope'] == 'current'
    assert items_q['run_status'] == 'queued'

    # 3) Run completed -> current vs explicit run_id
    drain(w)
    summary_cur = fetch_summary(c, d)
    items_cur = fetch_items(c, d)
    assert summary_cur['run_id'] is None
    assert summary_cur['resolved_run_id'] == r1['id']
    assert summary_cur['revision_scope'] == 'current'
    assert summary_cur['run_status'] == 'completed'
    assert items_cur['run_id'] is None
    assert items_cur['resolved_run_id'] == r1['id']
    assert items_cur['revision_scope'] == 'current'
    assert items_cur['run_status'] == 'completed'

    summary_run = fetch_summary(c, d, run_id=r1['id'])
    items_run = fetch_items(c, d, run_id=r1['id'])
    assert summary_run['run_id'] == r1['id']
    assert summary_run['resolved_run_id'] == r1['id']
    assert summary_run['revision_scope'] == 'run'
    assert summary_run['run_status'] == 'completed'
    assert items_run['run_id'] == r1['id']
    assert items_run['resolved_run_id'] == r1['id']
    assert items_run['revision_scope'] == 'run'
    assert items_run['run_status'] == 'completed'


def test_pagination_sort_filter_evidence_and_export_parities(env):
    c, s, r, w = env
    texts = [
        'Thư viện: điều hòa hỏng rất nóng',         # (2, 4) -> Negative, Service
        'Thư viện: phục vụ chậm buổi trưa',         # (2, 4) -> Negative, Service
        'Thư viện: nhân viên nhiệt tình',           # (1, 4) -> Positive, Service
        'Bình luận gay gắt trên diễn đàn',          # (3, 4) -> Toxic, Service
        'Thư viện: thông báo giờ mở cửa',           # (0, 4) -> Neutral, Service
        'Học phần: lịch thi đổi sát ngày',          # (2, 2) -> Negative, Academic
        'Học phần: bài giảng dễ hiểu',              # (1, 2) -> Positive, Academic
        'Học phần: câu hỏi lịch học',               # (2, 2) -> Negative, Academic (will edit review)
        'Tin tức học bổng cuối tháng',              # (0, 1) -> Neutral, News
    ]
    r.mapping = {
        texts[0]: (2, 4),
        texts[1]: (2, 4),
        texts[2]: (1, 4),
        texts[3]: (3, 4),
        texts[4]: (0, 4),
        texts[5]: (2, 2),
        texts[6]: (1, 2),
        texts[7]: (2, 2),
        texts[8]: (0, 1),
    }
    r.low_confidence_texts = {texts[6]}
    d = make_dataset(c, profile='neu', texts=texts)
    create_run(c, d)
    drain(w)

    # Review item 7 manually: change sentiment 2->1 and confirm topic 2, plus review item 0 both tasks.
    all_rows = fetch_items(c, d)['items']
    rev_resp = c.put(
        f"/api/v1/items/{all_rows[7]['id']}/review",
        json=dict(task='sentiment', status='corrected', label_id=1, expected_revision=1, expected_review_revision=0),
    )
    assert rev_resp.status_code == 200
    assert (
        c.put(
            f"/api/v1/items/{all_rows[0]['id']}/review",
            json=dict(task='sentiment', status='confirmed', label_id=2, expected_revision=1, expected_review_revision=0),
        ).status_code
        == 200
    )
    assert (
        c.put(
            f"/api/v1/items/{all_rows[0]['id']}/review",
            json=dict(task='topic', status='confirmed', label_id=4, expected_revision=1, expected_review_revision=0),
        ).status_code
        == 200
    )

    # Pagination & sort invariance on summary + attention
    summary_base = fetch_summary(c, d)
    summary_sorted = fetch_summary(c, d, sort='text', direction='desc', page=2, page_size=2)
    assert summary_sorted == summary_base

    page1 = fetch_items(c, d, page=1, page_size=3, sort='text', direction='desc')
    page2 = fetch_items(c, d, page=2, page_size=3, sort='text', direction='desc')
    assert page1['total'] == summary_base['total'] == 9
    assert page2['total'] == summary_base['total'] == 9
    assert len(page1['items']) == 3 and len(page2['items']) == 3
    assert {x['id'] for x in page1['items']}.isdisjoint({x['id'] for x in page2['items']})

    # NEU Toxic separation and small_sample checks on full effective summary
    att = summary_base['attention']
    _assert_attention_invariants(att, summary_base['total'])
    assert att['negative_label_id'] == 2
    assert att['toxic_label_id'] == 3
    assert att['eligible_count'] == summary_base['denominator']['cross'] == 9
    by_topic = {t['topic_id']: t for t in att['topics']}
    assert by_topic[4]['negative_count'] == 2
    assert by_topic[4]['toxic_count'] == 1
    assert by_topic[4]['eligible_count'] == 5
    assert by_topic[4]['small_sample'] is False
    assert by_topic[2]['negative_count'] == 1  # item 7 corrected from Negative(2) -> Positive(1)
    assert by_topic[2]['eligible_count'] == 3
    assert by_topic[2]['small_sample'] is True
    assert by_topic[1]['negative_count'] == 0
    assert by_topic[1]['eligible_count'] == 1
    assert [t['topic_id'] for t in att['topics']] == [4, 2, 1]

    # Compare effective vs AI across filter combinations + evidence drill-down + export membership
    filter_combos = [
        dict(label_source='effective'),
        dict(label_source='ai'),
        dict(label_source='effective', q='Thư viện'),
        dict(label_source='ai', q='Thư viện'),
        dict(label_source='effective', topic=4),
        dict(label_source='effective', review_status='unreviewed'),
        dict(label_source='effective', review_status='partial'),
        dict(label_source='effective', review_status='reviewed'),
        dict(label_source='effective', review_status='needs_review'),
        dict(label_source='ai', review_status='needs_review', q='Học phần'),
        dict(label_source='effective', q='khong-ton-tai-xyz'),
    ]
    for f in filter_combos:
        s_resp = fetch_summary(c, d, **f)
        i_resp = fetch_items(c, d, page=1, page_size=50, **f)
        exp_resp = c.post(f"/api/v1/datasets/{d['id']}/exports", json=dict(scope='filtered', **f))
        assert exp_resp.status_code == 201, exp_resp.text
        exp_json = exp_resp.json()

        a = s_resp['attention']
        _assert_attention_invariants(a, s_resp['total'])
        assert s_resp['total'] == i_resp['total'] == exp_json['row_count']
        assert a['eligible_count'] == s_resp['denominator']['cross']
        assert sum(t['topic_count'] for t in a['topics']) + a['missing_topic_count'] == s_resp['total']

        # Evidence drill-down parity for every topic row
        for topic_row in a['topics']:
            ev_params = dict(f)
            ev_params.update(
                topic=topic_row['topic_id'],
                sentiment=a['negative_label_id'],
                sort='source_row',
                direction='asc',
                page=1,
                page_size=50,
            )
            ev_resp = fetch_items(c, d, **ev_params)
            assert ev_resp['total'] == topic_row['negative_count']
            ev_rows = ev_resp['items']
            assert [x['source_row'] for x in ev_rows] == sorted(x['source_row'] for x in ev_rows)
            src = f.get('label_source', 'effective')
            for row in ev_rows:
                labels = row['effective'] if src == 'effective' else {
                    'sentiment': row['prediction']['sentiment']['label_id'],
                    'topic': row['prediction']['topic']['label_id'],
                }
                assert labels['topic'] == topic_row['topic_id']
                assert labels['sentiment'] == a['negative_label_id']


def test_sentiment_filter_keeps_non_negative_zero_and_negative_conditional_rate(env):
    c, s, r, w = env
    # 1) NEU: filter sentiment != Negative (Positive=1 and Toxic=3), and sentiment == Negative (2)
    neu_texts = ['Tiêu cực', 'Tích cực', 'Độc hại']
    r.mapping = {'Tiêu cực': (2, 4), 'Tích cực': (1, 4), 'Độc hại': (3, 4)}
    d_neu = make_dataset(c, profile='neu', texts=neu_texts)
    create_run(c, d_neu)
    drain(w)

    pos_only = fetch_summary(c, d_neu, sentiment=1)
    assert pos_only['total'] == 1
    assert pos_only['attention']['topics'] == [
        dict(
            topic_id=4,
            topic_count=1,
            eligible_count=1,
            negative_count=0,
            toxic_count=0,
            negative_rate=0.0,
            missing_sentiment_count=0,
            small_sample=True,
        )
    ]

    tox_only = fetch_summary(c, d_neu, sentiment=3)
    assert tox_only['total'] == 1
    assert tox_only['attention']['topics'] == [
        dict(
            topic_id=4,
            topic_count=1,
            eligible_count=1,
            negative_count=0,
            toxic_count=1,
            negative_rate=0.0,
            missing_sentiment_count=0,
            small_sample=True,
        )
    ]

    neg_only = fetch_summary(c, d_neu, sentiment=2)
    assert neg_only['total'] == 1
    assert neg_only['attention']['topics'] == [
        dict(
            topic_id=4,
            topic_count=1,
            eligible_count=1,
            negative_count=1,
            toxic_count=0,
            negative_rate=1.0,
            missing_sentiment_count=0,
            small_sample=True,
        )
    ]

    # 2) UIT: negative_label_id == 0, toxic_label_id is None, toxic_count is None
    uit_texts = ['Giảng viên chưa rõ', 'Cơ sở vật chất tốt']
    r.mapping = {'Giảng viên chưa rõ': (0, 0), 'Cơ sở vật chất tốt': (2, 2)}
    d_uit = make_dataset(c, profile='uit', texts=uit_texts)
    create_run(c, d_uit)
    drain(w)

    uit_all = fetch_summary(c, d_uit)
    assert uit_all['attention']['negative_label_id'] == 0
    assert uit_all['attention']['toxic_label_id'] is None
    assert [t['topic_id'] for t in uit_all['attention']['topics']] == [0, 2]
    assert all(t['toxic_count'] is None for t in uit_all['attention']['topics'])
    assert uit_all['attention']['topics'][0]['negative_rate'] == 1.0
    assert uit_all['attention']['topics'][1]['negative_rate'] == 0.0

    uit_pos = fetch_summary(c, d_uit, sentiment=2)
    assert uit_pos['total'] == 1
    assert uit_pos['attention']['topics'] == [
        dict(
            topic_id=2,
            topic_count=1,
            eligible_count=1,
            negative_count=0,
            toxic_count=None,
            negative_rate=0.0,
            missing_sentiment_count=0,
            small_sample=True,
        )
    ]

    uit_neg = fetch_summary(c, d_uit, sentiment=0)
    assert uit_neg['total'] == 1
    assert uit_neg['attention']['topics'][0]['negative_rate'] == 1.0
    assert uit_neg['attention']['topics'][0]['toxic_count'] is None
    assert fetch_items(c, d_uit, topic=0, sentiment=uit_all['attention']['negative_label_id'])['total'] == 1


def test_current_vs_historical_revision_edit_partial_error_run_and_manual_topic_only(env):
    c, s, r, w = env
    texts = ['Dòng một', 'Dòng hai', 'Dòng ba']
    r.mapping = {'Dòng một': (2, 4), 'Dòng hai': (2, 4), 'Dòng ba': (1, 2)}
    d = make_dataset(c, profile='neu', texts=texts)
    r1 = create_run(c, d)
    drain(w)

    initial_items = fetch_items(c, d)['items']

    # Edit text of item 0 -> revision 2 loses prediction in current view, kept in historical r1
    assert (
        c.patch(
            f"/api/v1/items/{initial_items[0]['id']}/text",
            json=dict(text='Dòng một đã sửa', expected_revision=1),
        ).status_code
        == 200
    )

    cur_after_edit = fetch_summary(c, d)
    assert cur_after_edit['resolved_run_id'] == r1['id']
    assert cur_after_edit['revision_scope'] == 'current'
    assert cur_after_edit['run_status'] == 'completed'
    assert cur_after_edit['attention']['filtered_count'] == 3
    assert cur_after_edit['attention']['eligible_count'] == 2
    assert cur_after_edit['attention']['missing_topic_count'] == 1

    # Manual topic-only review on edited item (still no sentiment) -> missing_sentiment_with_topic_count=1
    assert (
        c.put(
            f"/api/v1/items/{initial_items[0]['id']}/review",
            json=dict(task='topic', status='corrected', label_id=9, expected_revision=2, expected_review_revision=0),
        ).status_code
        == 200
    )
    cur_topic_only = fetch_summary(c, d)
    _assert_attention_invariants(cur_topic_only['attention'], 3)
    assert cur_topic_only['attention']['eligible_count'] == cur_topic_only['denominator']['cross'] == 2
    assert cur_topic_only['attention']['missing_topic_count'] == 0
    assert cur_topic_only['attention']['missing_sentiment_with_topic_count'] == 1
    by_topic_cur = {t['topic_id']: t for t in cur_topic_only['attention']['topics']}
    assert by_topic_cur[9] == dict(
        topic_id=9,
        topic_count=1,
        eligible_count=0,
        negative_count=0,
        toxic_count=0,
        negative_rate=None,
        missing_sentiment_count=1,
        small_sample=True,
    )

    # Under AI source, manual topic review is ignored -> item 0 remains in missing_topic_count
    ai_after_edit = fetch_summary(c, d, label_source='ai')
    assert ai_after_edit['attention']['eligible_count'] == 2
    assert ai_after_edit['attention']['missing_topic_count'] == 1
    assert ai_after_edit['attention']['missing_sentiment_with_topic_count'] == 0

    # Historical run r1 keeps original revision 1 membership and predictions
    hist_r1 = fetch_summary(c, d, run_id=r1['id'])
    assert hist_r1['resolved_run_id'] == r1['id']
    assert hist_r1['revision_scope'] == 'run'
    assert hist_r1['run_status'] == 'completed'
    assert hist_r1['attention']['filtered_count'] == 3
    assert hist_r1['attention']['eligible_count'] == 3
    assert hist_r1['attention']['missing_topic_count'] == 0
    assert hist_r1['attention']['topics'][0]['topic_id'] == 4
    assert hist_r1['attention']['topics'][0]['negative_count'] == 2
    hist_ev = fetch_items(
        c,
        d,
        run_id=r1['id'],
        topic=4,
        sentiment=hist_r1['attention']['negative_label_id'],
        sort='source_row',
        direction='asc',
    )
    assert hist_ev['total'] == 2
    assert hist_ev['revision_scope'] == 'run'
    assert hist_ev['resolved_run_id'] == r1['id']

    # Appending a new item after r1 affects current view only, not historical r1
    assert c.post(f"/api/v1/datasets/{d['id']}/items", json=dict(items=[dict(text='Dòng bốn mới thêm')])).status_code == 201
    cur_with_appended = fetch_summary(c, d)
    assert cur_with_appended['total'] == 4
    assert cur_with_appended['attention']['filtered_count'] == 4
    assert cur_with_appended['attention']['missing_topic_count'] == 1
    assert fetch_summary(c, d, run_id=r1['id'])['total'] == 3

    # Start partial new run r2 (item 0 succeeds on rev 2, item 1 fails, items 2 & 3 still queued): no fallback to r1!
    r.mapping['Dòng một đã sửa'] = (2, 4)
    r2 = create_run(c, d)
    assert r2['id'] != r1['id']
    assert w.run_once() is True  # processes item 0 (rev 2): AI=(2, 4), existing manual topic=9 -> effective=(2, 9)
    r.fail = True
    assert w.run_once() is True  # fails item 1; items 2 and 3 remain unprocessed

    partial_cur = fetch_summary(c, d)
    assert partial_cur['resolved_run_id'] == r2['id']
    assert partial_cur['revision_scope'] == 'current'
    assert partial_cur['run_status'] == 'queued'
    assert partial_cur['processed'] == 1
    assert partial_cur['errors'] == 1
    # Item 0 has AI sentiment=2 + manual topic=9; items 1..3 have no labels (no fallback to r1!)
    assert partial_cur['attention']['eligible_count'] == 1
    assert partial_cur['attention']['missing_topic_count'] == 3
    assert [t['topic_id'] for t in partial_cur['attention']['topics']] == [9]
    assert partial_cur['attention']['topics'][0]['negative_count'] == 1

    # Manual review of both tasks on failed item 1 counts for effective, NOT for ai
    assert (
        c.put(
            f"/api/v1/items/{initial_items[1]['id']}/review",
            json=dict(task='sentiment', status='corrected', label_id=2, expected_revision=1, expected_review_revision=0),
        ).status_code
        == 200
    )
    assert (
        c.put(
            f"/api/v1/items/{initial_items[1]['id']}/review",
            json=dict(task='topic', status='corrected', label_id=4, expected_revision=1, expected_review_revision=0),
        ).status_code
        == 200
    )

    partial_eff = fetch_summary(c, d, label_source='effective')
    assert partial_eff['errors'] == 1
    assert partial_eff['attention']['eligible_count'] == partial_eff['denominator']['cross'] == 2
    assert partial_eff['attention']['missing_topic_count'] == 2
    assert [(t['topic_id'], t['negative_count']) for t in partial_eff['attention']['topics']] == [(4, 1), (9, 1)]

    partial_ai = fetch_summary(c, d, label_source='ai')
    assert partial_ai['attention']['eligible_count'] == 1
    assert partial_ai['attention']['missing_topic_count'] == 3
    assert [(t['topic_id'], t['negative_count']) for t in partial_ai['attention']['topics']] == [(4, 1)]

    # Finish remaining 2 items (item 2 and item 3) with error so r2 enters terminal completed_with_errors
    assert w.run_once() is True
    assert w.run_once() is True
    assert w.run_once() is False
    done_err_cur = fetch_summary(c, d)
    assert done_err_cur['resolved_run_id'] == r2['id']
    assert done_err_cur['run_status'] == 'completed_with_errors'
    assert done_err_cur['errors'] == 3

    # Historical run r1 stays intact after r2 partial errors
    hist_after_r2 = fetch_summary(c, d, run_id=r1['id'])
    assert hist_after_r2['resolved_run_id'] == r1['id']
    assert hist_after_r2['revision_scope'] == 'run'
    assert hist_after_r2['run_status'] == 'completed'
    assert hist_after_r2['attention']['eligible_count'] == 3


def test_run_dataset_mismatch_and_invalid_filter_errors(env):
    c, s, r, w = env
    d1 = make_dataset(c, profile='neu', texts=['Dataset 1'])
    d2 = make_dataset(c, profile='neu', texts=['Dataset 2'])
    r2 = create_run(c, d2)

    for path in (f"/api/v1/datasets/{d1['id']}/summary", f"/api/v1/datasets/{d1['id']}/items"):
        resp = c.get(path, params={'run_id': r2['id']})
        assert resp.status_code == 422
        assert resp.json()['code'] == 'RUN_DATASET_MISMATCH'

        missing_run = c.get(path, params={'run_id': 'nonexistent-run'})
        assert missing_run.status_code == 404
        assert missing_run.json()['code'] == 'NOT_FOUND'

    assert c.get(f"/api/v1/datasets/{d1['id']}/summary", params={'label_source': 'reference'}).status_code == 422
    assert c.get(f"/api/v1/datasets/{d1['id']}/summary", params={'sentiment': 99}).json()['code'] == 'INVALID_FILTER'


def test_evidence_sort_source_row_tie_breaks_by_item_id_asc(env):
    c, s, r, w = env
    d = make_dataset(c, profile='neu', texts=['Placeholder'])
    with s.tx() as db:
        db.execute('DELETE FROM items WHERE dataset_id=?', (d['id'],))
        # Insert higher item_id first (smaller rowid) with identical source_row=1
        for item_id, rev_id, text in (
            ('item-z', 'rev-z', 'Phản hồi z'),
            ('item-a', 'rev-a', 'Phản hồi a'),
        ):
            db.execute(
                'INSERT INTO items(id, dataset_id, source_row, current_revision_id) VALUES(?,?,?,?)',
                (item_id, d['id'], 1, rev_id),
            )
            db.execute(
                'INSERT INTO revisions(id, item_id, revision, text, text_hash, metadata_json, created_at) VALUES(?,?,?,?,?,?,?)',
                (rev_id, item_id, 1, text, 'hash-' + item_id, '{}', '2026-11-10T00:00:00Z'),
            )
    r.mapping = {'Phản hồi z': (2, 4), 'Phản hồi a': (2, 4)}
    create_run(c, d)
    drain(w)

    ev = fetch_items(c, d, topic=4, sentiment=2, sort='source_row', direction='asc')
    assert ev['total'] == 2
    assert [row['id'] for row in ev['items']] == ['item-a', 'item-z']
