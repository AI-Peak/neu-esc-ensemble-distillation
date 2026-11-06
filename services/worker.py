"""Single local inference worker. Run with ``python -m services.worker``."""
import argparse
import math
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from services.storage.db import Store, TERMINAL, encode, now, profile_for, uid


class Worker:
    def __init__(self, runtime_dir=None, registry=None, batch_size=8, lease_seconds=60, cleanup_interval_seconds=30):
        self.store = Store(runtime_dir)
        if registry is None:
            from services.inference.registry import ModelRegistry
            registry = ModelRegistry(self.store.runtime / 'models')
        self.registry = registry
        self.batch_size = batch_size
        self.lease_seconds = lease_seconds
        self.owner = uid()
        self.stop_event = threading.Event()
        if not 0 < cleanup_interval_seconds <= 30:
            raise ValueError('Cleanup interval must be greater than zero and at most 30 seconds')
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self._next_cleanup = 0
        self._cleanup_lock = threading.Lock()

    def cleanup_if_due(self):
        if time.monotonic() < self._next_cleanup:
            return
        with self._cleanup_lock:
            if time.monotonic() < self._next_cleanup:
                return
            try:
                self.store.cleanup()
            except sqlite3.OperationalError as exc:
                # Retry maintenance on the next tick after SQLite's busy timeout.
                # Lock contention must not permanently kill the keepalive thread.
                if 'locked' not in str(exc).lower() and 'busy' not in str(exc).lower():
                    raise
            else:
                self._next_cleanup = time.monotonic() + self.cleanup_interval_seconds

    def heartbeat(self, job=None):
        with self.store.tx() as c:
            c.execute('INSERT INTO worker_status VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner,pid=excluded.pid,heartbeat_at=excluded.heartbeat_at,expires_at=excluded.expires_at', (self.owner, os.getpid(), now(), time.time()+max(15,self.lease_seconds)))
            if job:
                c.execute("UPDATE jobs SET heartbeat_at=?,lease_expires_at=? WHERE id=? AND attempt_id=? AND lease_owner=? AND status IN ('running','loading_model') AND lease_expires_at>?", (now(), time.time()+self.lease_seconds, job['id'], job['attempt_id'], self.owner, time.time()))

    @contextmanager
    def keepalive(self, job):
        done = threading.Event()
        def beat():
            while not done.wait(min(max(.05, min(5, self.lease_seconds/3)), self.cleanup_interval_seconds)):
                self.heartbeat(job)
                self.cleanup_if_due()
        thread = threading.Thread(target=beat, daemon=True)
        thread.start()
        try: yield
        finally:
            done.set(); thread.join(timeout=6)

    def claim(self):
        with self.store.tx() as c:
            self.store.recover(c)
            row = c.execute("SELECT * FROM jobs WHERE status='queued' OR (status IN ('running','loading_model') AND lease_owner=? AND lease_expires_at>?) ORDER BY priority DESC,created_at LIMIT 1", (self.owner,time.time())).fetchone()
            if not row: return None
            attempt = row['attempt_id'] + (1 if row['status'] == 'queued' else 0)
            c.execute("UPDATE jobs SET status='loading_model',attempt_id=?,lease_owner=?,lease_expires_at=?,heartbeat_at=?,updated_at=? WHERE id=?", (attempt,self.owner,time.time()+self.lease_seconds,now(),now(),row['id']))
            c.execute("UPDATE runs SET status='loading_model' WHERE id=?", (row['run_id'],))
            return dict(c.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())

    def valid_lease(self, c, job):
        return c.execute("SELECT * FROM jobs WHERE id=? AND attempt_id=? AND lease_owner=? AND lease_expires_at>? AND status IN ('loading_model','running')", (job['id'],job['attempt_id'],self.owner,time.time())).fetchone()

    def finish(self, c, job, status, error=None):
        c.execute('UPDATE jobs SET status=?,error=?,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?', (status,error,now(),job['id']))
        c.execute('UPDATE runs SET status=? WHERE id=?', (status,job['run_id']))
        self.store.expire_quick(c,job['run_id'])

    @staticmethod
    def validate_prediction(prediction, request, run, profile):
        if any(prediction.get(k) != request[k] for k in ('item_id','revision_id')):
            raise ValueError('Prediction IDs do not match input')
        if any(prediction.get(k) != run[k] for k in ('model_id','model_version','schema_id')):
            raise ValueError('Prediction model/schema differs from frozen run')
        for task in ('sentiment','topic'):
            value = prediction.get(task,{})
            scores = value.get('scores',[])
            if len(scores) != len(profile[task]) or any(type(s) not in (float,int) or not math.isfinite(s) or s < 0 or s > 1 for s in scores) or abs(sum(scores)-1) > .001:
                raise ValueError('Invalid probability distribution')
            if type(value.get('label_id')) is not int or value['label_id'] != max(range(len(scores)),key=scores.__getitem__):
                raise ValueError('Invalid prediction label')
        if type(prediction.get('truncated')) is not bool or type(prediction.get('token_count_before_truncation')) is not int or prediction['token_count_before_truncation'] < 0:
            raise ValueError('Invalid truncation metadata')
        if not isinstance(prediction.get('warnings'),list) or any(not isinstance(x,str) for x in prediction['warnings']):
            raise ValueError('Invalid warnings')
        if not isinstance(prediction.get('duration_ms'), (int,float)) or not math.isfinite(prediction['duration_ms']) or prediction['duration_ms'] < 0:
            raise ValueError('Invalid inference duration')

    def run_once(self):
        """Process at most one microbatch, allowing quick jobs to preempt between batches."""
        self.heartbeat()
        self.cleanup_if_due()
        job = self.claim()
        if not job:
            return False
        with self.keepalive(job):
            with self.store.tx() as c:
                live = self.valid_lease(c,job)
                if not live: return True
                if live['cancel_requested']:
                    self.finish(c,job,'cancelled'); return True
                run = self.store.run(job['run_id'],c)
                dataset = self.store.require_dataset(c,run['dataset_id'])
                rows = c.execute('SELECT ri.item_id,ri.revision_id,r.text FROM run_items ri JOIN revisions r ON r.id=ri.revision_id WHERE ri.run_id=? AND ri.error IS NULL AND NOT EXISTS(SELECT 1 FROM predictions p WHERE p.run_id=ri.run_id AND p.item_id=ri.item_id) ORDER BY (SELECT source_row FROM items WHERE id=ri.item_id) LIMIT ?', (run['id'],self.batch_size)).fetchall()
                inputs = [dict(r) for r in rows]
                c.execute("UPDATE jobs SET status='running' WHERE id=?",(job['id'],))
                c.execute("UPDATE runs SET status='running' WHERE id=?",(run['id'],))
            if not inputs:
                with self.store.tx() as c:
                    live = self.valid_lease(c,job)
                    if live: self.finish(c,job,'completed_with_errors' if live['failed'] else 'completed')
                return True
            outputs, failure = [], None
            try:
                status = self.registry.status(dataset['profile'])
                if not status.get('available') or any(status.get(k) != run[k] for k in ('model_id','model_version','schema_id')):
                    raise ValueError('Frozen model version is unavailable')
                outputs = self.registry.predict(dataset['profile'],inputs)
                by_id = {(x.get('item_id'),x.get('revision_id')):x for x in outputs}
                if len(outputs) != len(inputs) or len(by_id) != len(inputs): raise ValueError('Prediction count mismatch')
                outputs = [by_id[(x['item_id'],x['revision_id'])] for x in inputs]
                for output, request in zip(outputs,inputs):
                    self.validate_prediction(output,request,run,profile_for(dataset['profile']))
            except Exception as exc:
                # Never persist exception strings which could contain private input text.
                failure = 'Inference failed (' + type(exc).__name__ + '). Check the installed model and retry.'
            with self.store.tx() as c:
                live = self.valid_lease(c,job)
                if not live: return True
                if live['cancel_requested']:
                    self.finish(c,job,'cancelled'); return True
                for n, request in enumerate(inputs):
                    if failure:
                        c.execute('UPDATE run_items SET error=? WHERE run_id=? AND item_id=?', (failure,run['id'],request['item_id']))
                    else:
                        c.execute('INSERT INTO predictions VALUES(?,?,?,?,?,?)', (uid(),run['id'],request['item_id'],request['revision_id'],encode(outputs[n]),now()))
                completed = c.execute('SELECT COUNT(*) FROM predictions WHERE run_id=?',(run['id'],)).fetchone()[0]
                failed = c.execute('SELECT COUNT(*) FROM run_items WHERE run_id=? AND error IS NOT NULL',(run['id'],)).fetchone()[0]
                c.execute('UPDATE jobs SET completed=?,failed=?,heartbeat_at=?,updated_at=? WHERE id=?',(completed,failed,now(),now(),job['id']))
                c.execute('UPDATE runs SET completed=?,failed=? WHERE id=?',(completed,failed,run['id']))
                if completed+failed == run['total']:
                    self.finish(c,job,'completed_with_errors' if failed else 'completed')
                else:
                    # Release ownership in the same fenced transaction as progress.
                    # A quick job may now take any amount of time without expiring
                    # a healthy bulk job's suspended lease. The next queued claim
                    # advances attempt_id, so the previous batch cannot commit again.
                    c.execute("UPDATE jobs SET status='queued',lease_owner=NULL,lease_expires_at=NULL WHERE id=?", (job['id'],))
                    c.execute("UPDATE runs SET status='queued' WHERE id=?", (run['id'],))
        return True

    def run(self):
        with self.process_lock():
            while not self.stop_event.is_set():
                if not self.run_once(): self.stop_event.wait(.5)

    @contextmanager
    def process_lock(self):
        path = self.store.runtime / 'worker.lock'
        handle = path.open('a+b')
        handle.seek(0); handle.write(b'0'); handle.flush(); handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise RuntimeError('Another inference worker already owns this runtime.')
        try: yield
        finally:
            with self.store.tx() as c:
                c.execute('UPDATE worker_status SET expires_at=0 WHERE owner=?',(self.owner,))
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_UN)
            handle.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir')
    parser.add_argument('--once',action='store_true')
    args = parser.parse_args()
    worker = Worker(args.runtime_dir)
    if args.once:
        with worker.process_lock(): worker.run_once()
    else:
        try: worker.run()
        except KeyboardInterrupt: pass


if __name__ == '__main__': main()
