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
