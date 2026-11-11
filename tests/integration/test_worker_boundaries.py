import threading
import time

import pytest

from services.storage.db import Store
from services.worker import Worker
from tests.support import TestOnlyRegistry


def create_run(store, registry):
    dataset = store.create_dataset({"name": "Worker boundary", "profile": "neu",
                                    "items": [{"text": "Kiểm tra công việc một"}, {"text": "Kiểm tra công việc hai"}]})
    return store.create_run(dataset["id"], registry.status("neu"))


def test_cancel_during_inference_discards_uncommitted_batch_and_retry_is_unique(tmp_path):
    store = Store(tmp_path)

    class CancellingRegistry(TestOnlyRegistry):
        should_cancel = True

        def predict(self, profile, items):
            outputs = super().predict(profile, items)
            if self.should_cancel:
                store.cancel(run["job_id"])
            return outputs

    registry = CancellingRegistry()
    run = create_run(store, registry)
    worker = Worker(tmp_path, registry)
    worker.run_once()
    job = store.job(run["job_id"])
    assert job["status"] == "cancelled" and job["completed"] == 0
    registry.should_cancel = False
    store.retry(job["id"], registry.status("neu"))
    worker.run_once()
    assert store.job(job["id"])["completed"] == 2
    assert store.job(job["id"])["status"] == "completed"
    with store.connect() as connection:
        assert connection.execute("SELECT count(*) FROM predictions").fetchone()[0] == 2


def test_keepalive_renews_lease_during_slow_inference(tmp_path):
    entered, release = threading.Event(), threading.Event()

    class SlowRegistry(TestOnlyRegistry):
        def predict(self, profile, items):
            entered.set()
            assert release.wait(5), "test timed out waiting for release"
            return super().predict(profile, items)

    registry = SlowRegistry()
    store = Store(tmp_path)
    run = create_run(store, registry)
    worker = Worker(tmp_path, registry, lease_seconds=0.6)
    thread = threading.Thread(target=worker.run_once)
    thread.start()
    try:
        assert entered.wait(5)
        time.sleep(1.3)  # Longer than the original lease; the heartbeat must renew it.
        store.cleanup()
        job = store.job(run["job_id"])
        assert job["status"] == "running"
        assert job["lease_expires_at"] > time.time()
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert store.job(run["job_id"])["status"] == "completed"


def quick_run(store,registry,text='Private quick input'):
    dataset=store.create_dataset(dict(name='Quick',profile='neu',items=[dict(text=text)]),temporary=True)
    return store.create_run(dataset['id'],registry.status('neu'))


def test_bulk_yields_lease_and_resumes_after_repeated_long_quick_jobs(tmp_path):
    class SlowQuickRegistry(TestOnlyRegistry):
        slow=False
        def predict(self,profile,items):
            if self.slow: time.sleep(.35)
            return super().predict(profile,items)
    registry=SlowQuickRegistry(); store=Store(tmp_path)
    bulk=create_run(store,registry)
    worker=Worker(tmp_path,registry,batch_size=1,lease_seconds=.2)
    worker.run_once()
    yielded=store.job(bulk['job_id'])
    assert yielded['status']=='queued' and yielded['lease_owner'] is None
    registry.slow=True
    for _ in range(3):
        quick=quick_run(store,registry)
        worker.run_once()
        assert store.job(quick['job_id'])['status']=='completed'
        bulk_job=store.job(bulk['job_id'])
        assert bulk_job['status']=='queued' and bulk_job['completed']==1
    registry.slow=False
    worker.run_once()
    assert store.job(bulk['job_id'])['status']=='completed'
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM predictions WHERE run_id=?',(bulk['id'],)).fetchone()[0]==2


def test_yield_fences_previous_claim_and_cancel_retry_preserves_committed_rows(tmp_path):
    registry=TestOnlyRegistry(); store=Store(tmp_path)
    run=create_run(store,registry); worker=Worker(tmp_path,registry,batch_size=1)
    old_claim=worker.claim()
    worker.run_once()
    with store.tx() as db: assert worker.valid_lease(db,old_claim) is None
    cancelled=store.cancel(run['job_id'])
    assert cancelled['status']=='cancelled' and cancelled['completed']==1
    store.retry(run['job_id'],registry.status('neu'))
    next_claim=worker.claim()
    assert next_claim['attempt_id']>old_claim['attempt_id']
    with store.tx() as db: assert worker.valid_lease(db,old_claim) is None
    worker.run_once()
    assert store.job(run['job_id'])['status']=='completed'
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]==2


@pytest.mark.parametrize('continuous_backlog',[False,True])
def test_scheduled_cleanup_runs_during_inference_and_backlog(tmp_path,continuous_backlog):
    entered,release,cleaned=threading.Event(),threading.Event(),threading.Event()
    class BlockingRegistry(TestOnlyRegistry):
        block=False
        def predict(self,profile,items):
            if self.block:
                entered.set()
                assert release.wait(5)
            return super().predict(profile,items)
    registry=BlockingRegistry(); store=Store(tmp_path)
    expired=quick_run(store,registry); Worker(tmp_path,registry).run_once()
    durable=store.create_dataset(dict(name='Saved',profile='neu',items=[dict(text='Private quick input')]))
    worker=Worker(tmp_path,registry,batch_size=1,lease_seconds=.3,cleanup_interval_seconds=.04)
    bulk=create_run(store,registry)
    active=quick_run(store,registry,'Currently active private input')
    with store.tx() as db:
        db.execute('UPDATE datasets SET expires_at=? WHERE id=(SELECT dataset_id FROM runs WHERE id=?)',
                   (time.time()+.06,expired['id']))
        # Even an old expiry marker must never delete queued/running work.
        db.execute('UPDATE datasets SET expires_at=? WHERE id=(SELECT dataset_id FROM runs WHERE id=?)',
                   (time.time()-1,active['id']))
    original_cleanup=worker.store.cleanup
    def observe_cleanup():
        original_cleanup()
        with store.connect() as db:
            if not db.execute('SELECT 1 FROM jobs WHERE id=?',(expired['job_id'],)).fetchone(): cleaned.set()
    worker.store.cleanup=observe_cleanup
    if continuous_backlog:
        # Every call has pending work; expiration must not depend on an idle poll.
        for _ in range(12):
            quick_run(store,registry,text='Backlog quick input')
            worker.run_once()
            if cleaned.wait(.02): break
    else:
        registry.block=True
        thread=threading.Thread(target=worker.run_once); thread.start()
        try:
            assert entered.wait(5)
            assert cleaned.wait(2), 'maintenance did not expire payload during blocked inference'
            assert store.job(active['job_id'])['status']=='running'
        finally:
            release.set(); thread.join(5)
        assert not thread.is_alive()
    assert cleaned.is_set()
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM revisions WHERE text=?',('Private quick input',)).fetchone()[0]==1
        assert db.execute('SELECT 1 FROM datasets WHERE id=?',(durable['id'],)).fetchone()
        assert db.execute('SELECT 1 FROM jobs WHERE id=?',(active['job_id'],)).fetchone()


def _create_sensitivity_on_durable(store, registry, text='Phản hồi chất lượng rất tốt nhé', needle='rất tốt', key=None):
    import hashlib
    ds = store.create_dataset({'name': 'Sensitivity Source', 'profile': 'neu', 'items': [{'text': text}]})
    item = store.item(store.query_items(ds['id'], {})[0]['id'])
    start = text.index(needle)
    end = start + len(needle)
    body = {
        'revision_id': item['revision_id'],
        'expected_revision': item['revision'],
        'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        'run_id': None,
        'source_prediction_id': None,
        'selection': {
            'start_utf16': len(text[:start].encode('utf-16-le')) // 2,
            'end_utf16': len(text[:end].encode('utf-16-le')) // 2,
            'text': needle,
        },
    }
    exp = store.create_sensitivity_experiment(
        item['id'],
        body,
        key or f"wb-key-{item['id']}",
        execution_resolver=registry.execution_identity,
    )
    return ds, item, exp


def test_sensitivity_atomic_pair_with_batch_size_one_and_priority_preemption(tmp_path):
    registry = TestOnlyRegistry()
    store = Store(tmp_path)
    bulk = create_run(store, registry)
    worker = Worker(tmp_path, registry, batch_size=1)

    # Complete 1 of 2 bulk items first.
    assert worker.run_once() is True
    assert store.job(bulk['job_id'])['completed'] == 1
    assert store.job(bulk['job_id'])['status'] == 'queued'

    # Create sensitivity experiment (priority=1) with texts yielding distinct TestOnlyRegistry winners.
    src_ds, src_item, exp = _create_sensitivity_on_durable(
        store,
        registry,
        text='Dịch vụ giảng dạy rất tốt',
        needle='rất tốt',
        key='wb-priority-1',
    )

    # Single run_once() preempts bulk AND completes BOTH baseline & variant atomically even when batch_size=1,
    # while TestOnlyRegistry reverses predict() output order [variant, baseline].
    assert worker.run_once() is True
    done_exp = store.get_sensitivity_experiment(exp['experiment_id'], execution_resolver=registry.execution_identity)
    assert done_exp['status'] == 'completed'
    assert done_exp['completed'] == 2 and done_exp['failed'] == 0
    assert done_exp['result']['baseline']['text'] == 'Dịch vụ giảng dạy rất tốt'
    assert done_exp['result']['variant']['text'] == 'Dịch vụ giảng dạy '
    assert done_exp['result']['baseline']['prediction']['token_count_before_truncation'] == 8
    assert done_exp['result']['variant']['prediction']['token_count_before_truncation'] == 6
    # Bulk job stays cleanly paused at 1/2 until next run_once() finishes it.
    assert store.job(bulk['job_id'])['completed'] == 1

    assert worker.run_once() is True
    assert store.job(bulk['job_id'])['status'] == 'completed'
    assert store.job(bulk['job_id'])['completed'] == 2
    assert store.item(src_item['id'])['prediction'] is None


@pytest.mark.parametrize(
    'corruption',
    [
        'partial_one_prediction',
        'duplicate_id',
        'wrong_item_id',
        'wrong_revision_id',
        'mismatched_execution_identity',
        'non_bool_input_equal_none',
        'non_bool_input_equal_int',
        'nan_scores',
        'scores_sum_wrong',
        'wrong_schema_id',
        'corrupt_db_preflight',
    ],
)
def test_sensitivity_malformed_or_partial_pair_result_never_commits_half_pair(tmp_path, corruption):
    registry = TestOnlyRegistry()
    store = Store(tmp_path)
    _, _, exp = _create_sensitivity_on_durable(store, registry, key=f'bad-{corruption}')
    worker = Worker(tmp_path, registry, batch_size=1)

    if corruption == 'partial_one_prediction':
        registry.pair_bad = lambda preds, items: preds.pop()
    elif corruption == 'duplicate_id':
        def dup(preds, items):
            preds[1]['item_id'] = preds[0]['item_id']
            preds[1]['revision_id'] = preds[0]['revision_id']
        registry.pair_bad = dup
    elif corruption == 'wrong_item_id':
        registry.pair_bad = lambda preds, items: preds[0].update(item_id='unknown-item')
    elif corruption == 'wrong_revision_id':
        registry.pair_bad = lambda preds, items: preds[0].update(revision_id='unknown-rev')
    elif corruption == 'mismatched_execution_identity':
        registry.pair_returned_identity = {**registry.execution_identity('neu'), 'model_version': 'other-v99'}
    elif corruption == 'non_bool_input_equal_none':
        registry.pair_result_override = lambda res, *_: {**res, 'model_input_equal': None}
    elif corruption == 'non_bool_input_equal_int':
        registry.pair_result_override = lambda res, *_: {**res, 'model_input_equal': 1}
    elif corruption == 'nan_scores':
        registry.pair_bad = lambda preds, items: preds[0]['sentiment'].update(scores=[float('nan'), 0.5, 0.5, 0.0])
    elif corruption == 'scores_sum_wrong':
        registry.pair_bad = lambda preds, items: preds[0]['sentiment'].update(scores=[0.1, 0.1, 0.1, 0.1])
    elif corruption == 'wrong_schema_id':
        registry.pair_bad = lambda preds, items: preds[0].update(schema_id='uit-v1')
    elif corruption == 'corrupt_db_preflight':
        run_id = store.job(exp['job_id'])['run_id']
        with store.tx() as db:
            db.execute("UPDATE run_items SET error='preexisting corruption' WHERE run_id=?", (run_id,))

    assert worker.run_once() is True
    failed_exp = store.get_sensitivity_experiment(exp['experiment_id'], execution_resolver=registry.execution_identity)
    assert failed_exp['status'] == 'failed'
    assert failed_exp['completed'] == 0 and failed_exp['failed'] == 2
    assert failed_exp['result'] is None
    assert failed_exp['error'] is not None
    assert failed_exp['error']['code'] == 'INVALID_PAIR_RESULT'
    assert failed_exp['expires_at'] is not None
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM predictions WHERE run_id=?', (store.job(exp['job_id'])['run_id'],)).fetchone()[0] == 0


def test_sensitivity_exception_sanitizes_private_text_and_detects_identity_change(tmp_path):
    registry = TestOnlyRegistry()
    store = Store(tmp_path)
    secret = 'SECRET_WORKER_SENSITIVITY_TEXT_ABC'
    _, _, exp1 = _create_sensitivity_on_durable(
        store,
        registry,
        text=f'Phản hồi {secret} cần bảo mật',
        needle=secret,
        key='wb-secret-fail',
    )
    registry.pair_fail = RuntimeError(f'Explosion with {secret}')
    worker = Worker(tmp_path, registry, batch_size=1)
    assert worker.run_once() is True

    res1 = store.get_sensitivity_experiment(exp1['experiment_id'], execution_resolver=registry.execution_identity)
    job1 = store.job(exp1['job_id'])
    assert res1['status'] == 'failed' and res1['error']['code'] == 'INFERENCE_FAILED' and res1['result'] is None
    assert secret not in str(res1['error'])
    assert secret not in str(job1)
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM predictions WHERE run_id=?', (job1['run_id'],)).fetchone()[0] == 0

    # Active bundle swapped between enqueue and worker execution -> MODEL_IDENTITY_CHANGED.
    registry.pair_fail = False
    _, _, exp2 = _create_sensitivity_on_durable(store, registry, key='wb-ident-swap')
    registry.model_version = 'software-test-only-v99'
    assert worker.run_once() is True
    res2 = store.get_sensitivity_experiment(exp2['experiment_id'], execution_resolver=registry.execution_identity)
    assert res2['status'] == 'failed' and res2['error']['code'] == 'MODEL_IDENTITY_CHANGED' and res2['result'] is None


def test_sensitivity_cancel_during_inference_and_retry_keeps_frozen_snapshot(tmp_path):
    registry = TestOnlyRegistry()
    store = Store(tmp_path)
    _, _, exp = _create_sensitivity_on_durable(store, registry, key='wb-cancel-retry')
    registry.pair_hook = lambda *_: store.cancel(exp['job_id'])
    worker = Worker(tmp_path, registry, batch_size=1)
    assert worker.run_once() is True

    cancelled = store.get_sensitivity_experiment(exp['experiment_id'], execution_resolver=registry.execution_identity)
    assert cancelled['status'] == 'cancelled' and cancelled['completed'] == 0 and cancelled['result'] is None
    assert cancelled['expires_at'] is not None
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0] == 0

    registry.pair_hook = None
    store.retry(exp['job_id'], execution_resolver=registry.execution_identity)
    assert store.get_sensitivity_experiment(exp['experiment_id'])['expires_at'] is None
    assert worker.run_once() is True

    done = store.get_sensitivity_experiment(exp['experiment_id'], execution_resolver=registry.execution_identity)
    assert done['status'] == 'completed' and done['completed'] == 2 and done['result'] is not None
    assert done['source'] == cancelled['source']
    assert done['selection'] == cancelled['selection']
    assert done['execution'] == cancelled['execution']
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0] == 2


def test_sensitivity_lease_recovery_fences_stale_worker_and_allows_retry(tmp_path):
    registry = TestOnlyRegistry()
    store = Store(tmp_path)
    _, _, exp = _create_sensitivity_on_durable(store, registry, key='wb-lease-fence')
    worker1 = Worker(tmp_path, registry, batch_size=1)

    interrupted_seen = {}

    def expire_and_steal(*_):
        with store.tx() as db:
            db.execute('UPDATE jobs SET lease_expires_at=? WHERE id=?', (time.time() - 1, exp['job_id']))
        store.cleanup()
        interrupted_seen['state'] = store.get_sensitivity_experiment(
            exp['experiment_id'], execution_resolver=registry.execution_identity
        )
        store.retry(exp['job_id'], execution_resolver=registry.execution_identity)

    registry.pair_hook = expire_and_steal
    assert worker1.run_once() is True
    assert interrupted_seen['state']['status'] == 'interrupted'
    assert interrupted_seen['state']['error']['code'] == 'JOB_INTERRUPTED'
    assert interrupted_seen['state']['result'] is None
    # Stale worker1 commit was fenced; 0 predictions exist.
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0] == 0

    registry.pair_hook = None
    worker2 = Worker(tmp_path, registry, batch_size=1)
    assert worker2.run_once() is True
    done = store.get_sensitivity_experiment(exp['experiment_id'], execution_resolver=registry.execution_identity)
    assert done['status'] == 'completed' and done['error'] is None and done['result'] is not None
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM predictions').fetchone()[0] == 2


def test_sensitivity_source_deleted_during_pair_inference_leaves_no_orphans(tmp_path):
    registry = TestOnlyRegistry()
    store = Store(tmp_path)
    src_ds, _, exp = _create_sensitivity_on_durable(store, registry, key='wb-delete-race')
    registry.pair_hook = lambda *_: store.delete_dataset(src_ds['id'])
    worker = Worker(tmp_path, registry, batch_size=1)

    assert worker.run_once() is True
    with store.connect() as db:
        for table in ('datasets', 'items', 'revisions', 'runs', 'run_items', 'predictions', 'jobs', 'sensitivity_experiments', 'idempotency'):
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


def test_sensitivity_ttl_expiry_under_continuous_worker_backlog(tmp_path):
    registry = TestOnlyRegistry()
    store = Store(tmp_path)
    durable_ds, _, expired_exp = _create_sensitivity_on_durable(store, registry, key='wb-ttl-backlog')
    # Run initial experiment to completion first.
    Worker(tmp_path, registry, batch_size=1).run_once()
    assert store.get_sensitivity_experiment(expired_exp['experiment_id'])['status'] == 'completed'

    # Set temp dataset expiry into the past and keep worker continuously busy with backlog quick jobs.
    with store.tx() as db:
        db.execute(
            'UPDATE datasets SET expires_at=? WHERE id=(SELECT temporary_dataset_id FROM sensitivity_experiments WHERE job_id=?)',
            (time.time() - 1, expired_exp['job_id']),
        )

    worker = Worker(tmp_path, registry, batch_size=1, lease_seconds=0.3, cleanup_interval_seconds=0.04)
    cleaned = threading.Event()
    orig_cleanup = worker.store.cleanup

    def observe():
        orig_cleanup()
        with store.connect() as db:
            has_exp = db.execute('SELECT 1 FROM sensitivity_experiments WHERE job_id=?', (expired_exp['job_id'],)).fetchone()
            has_idem = db.execute("SELECT 1 FROM idempotency WHERE key='wb-ttl-backlog' AND operation='sensitivity'").fetchone()
            if not has_exp and not has_idem:
                cleaned.set()

    worker.store.cleanup = observe
    for _ in range(12):
        quick_run(store, registry, text='Backlog quick input')
        worker.run_once()
        if cleaned.wait(0.02):
            break

    assert cleaned.is_set()
    with store.connect() as db:
        assert db.execute('SELECT 1 FROM datasets WHERE id=?', (durable_ds['id'],)).fetchone()
        assert db.execute('SELECT COUNT(*) FROM sensitivity_experiments WHERE job_id=?', (expired_exp['job_id'],)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM idempotency WHERE key='wb-ttl-backlog' AND operation='sensitivity'").fetchone()[0] == 0
