"""Single local inference worker. Run with ``python -m services.worker``."""
import argparse
import json
import math
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from services.storage.db import Store, TERMINAL, encode, now, profile_for, uid
from services.attribution_contract import COMPUTE_SECONDS


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
                if 'source_job_id' in job:
                    c.execute("UPDATE attribution_jobs SET heartbeat_at=?,lease_expires_at=? WHERE id=? AND attempt_id=? AND lease_owner=? AND status='running' AND lease_expires_at>?", (now(), time.time()+self.lease_seconds, job['id'], job['attempt_id'], self.owner, time.time()))
                else:
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

    def claim_attribution(self):
        with self.store.tx() as c:
            self.store.recover(c)
            row = c.execute("SELECT * FROM attribution_jobs WHERE status='queued' OR (status='running' AND lease_owner=? AND lease_expires_at>?) ORDER BY created_at LIMIT 1", (self.owner, time.time())).fetchone()
            if not row:
                return None
            if c.execute("SELECT 1 FROM attribution_jobs WHERE status='running' AND lease_owner!=? AND lease_expires_at>?", (self.owner,time.time())).fetchone():
                return None
            attempt = row['attempt_id'] + (1 if row['status'] == 'queued' else 0)
            c.execute("UPDATE attribution_jobs SET status='running',attempt_id=?,lease_owner=?,lease_expires_at=?,heartbeat_at=?,updated_at=?,compute_started_at=COALESCE(compute_started_at,?),compute_deadline=COALESCE(compute_deadline,MIN(?,expires_at)) WHERE id=?", (attempt, self.owner, time.time()+self.lease_seconds, now(), now(), time.time(),time.time()+COMPUTE_SECONDS,row['id']))
            return dict(c.execute('SELECT * FROM attribution_jobs WHERE id=?', (row['id'],)).fetchone())

    def valid_lease(self, c, job):
        return c.execute("SELECT * FROM jobs WHERE id=? AND attempt_id=? AND lease_owner=? AND lease_expires_at>? AND status IN ('loading_model','running')", (job['id'],job['attempt_id'],self.owner,time.time())).fetchone()

    def valid_attribution_lease(self, c, attr_job):
        return c.execute("SELECT * FROM attribution_jobs WHERE id=? AND attempt_id=? AND lease_owner=? AND lease_expires_at>? AND status='running'", (attr_job['id'], attr_job['attempt_id'], self.owner, time.time())).fetchone()

    def finish(self, c, job, status, error=None):
        c.execute('UPDATE jobs SET status=?,error=?,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?', (status,error,now(),job['id']))
        c.execute('UPDATE runs SET status=? WHERE id=?', (status,job['run_id']))
        self.store.expire_quick(c,job['run_id'])

    def finish_attribution(self, c, attr_job, status, error_code=None, error_message=None):
        c.execute('UPDATE attribution_jobs SET status=?,error_code=?,error_message=?,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?', (status, error_code, error_message, now(), attr_job['id']))

    @staticmethod
    def validate_prediction(prediction, request, run, profile):
        if any(prediction.get(k) != request[k] for k in ('item_id','revision_id')):
            raise ValueError('Prediction IDs do not match input')
        if any(prediction.get(k) != run[k] for k in ('model_id','model_version','schema_id')):
            raise ValueError('Prediction model/schema differs from frozen run')
        for task in ('sentiment','topic'):
            value = prediction.get(task)
            if not isinstance(value, dict):
                raise ValueError('Invalid prediction task payload')
            scores = value.get('scores',[])
            if len(scores) != len(profile[task]) or any(type(s) not in (float,int) or not math.isfinite(s) or s < 0 or s > 1 for s in scores) or abs(sum(scores)-1) > .001:
                raise ValueError('Invalid probability distribution')
            if type(value.get('label_id')) is not int or value['label_id'] != max(range(len(scores)),key=scores.__getitem__):
                raise ValueError('Invalid prediction label')
        if type(prediction.get('truncated')) is not bool or type(prediction.get('token_count_before_truncation')) is not int or prediction['token_count_before_truncation'] < 0:
            raise ValueError('Invalid truncation metadata')
        if not isinstance(prediction.get('warnings'),list) or any(not isinstance(x,str) for x in prediction['warnings']):
            raise ValueError('Invalid warnings')
        if type(prediction.get('duration_ms')) not in (int, float) or not math.isfinite(prediction['duration_ms']) or prediction['duration_ms'] < 0:
            raise ValueError('Invalid inference duration')

    def _fail_sensitivity_tx(self, c, job, run, context, error_code):
        safe_error = f'Sensitivity pair failed ({error_code}).'
        context_next = dict(context)
        context_next['attempt'] = {'error_code': error_code, 'model_input_equal': None}
        stamp = now()
        c.execute('UPDATE sensitivity_experiments SET context_json=? WHERE job_id=?', (encode(context_next), job['id']))
        c.execute('UPDATE run_items SET error=? WHERE run_id=?', (safe_error, run['id']))
        c.execute('UPDATE jobs SET completed=0,failed=2,heartbeat_at=?,updated_at=? WHERE id=?', (stamp, stamp, job['id']))
        c.execute('UPDATE runs SET completed=0,failed=2 WHERE id=?', (run['id'],))
        self.finish(c, job, 'failed', error=safe_error)

    def _run_sensitivity_once(self, job, run, dataset, exp, inputs, expected_identity):
        pair_outputs = None
        model_input_equal = None
        error_code = None
        pair_result = None
        try:
            pair_result = self.registry.predict_pair(dataset['profile'], inputs, expected_identity)
        except Exception as exc:
            # Never persist exception strings which could contain private input text.
            from services.inference.registry import ModelIdentityChanged
            if isinstance(exc, ModelIdentityChanged) or type(exc).__name__ == 'ModelIdentityChanged':
                error_code = 'MODEL_IDENTITY_CHANGED'
            else:
                error_code = 'INFERENCE_FAILED'

        if error_code is None:
            try:
                if not isinstance(pair_result, dict):
                    raise ValueError('Pair result must be an object')
                if pair_result.get('execution_identity') != expected_identity:
                    raise ValueError('Returned execution identity mismatch')
                if type(pair_result.get('model_input_equal')) is not bool:
                    raise ValueError('model_input_equal must be a bool')
                raw_preds = pair_result.get('predictions')
                if not isinstance(raw_preds, list) or len(raw_preds) != 2:
                    raise ValueError('Pair predictions must contain exactly 2 entries')
                by_id = {}
                for pred in raw_preds:
                    if not isinstance(pred, dict):
                        raise ValueError('Prediction entry must be an object')
                    key = (pred.get('item_id'), pred.get('revision_id'))
                    if key in by_id:
                        raise ValueError('Duplicate pair prediction IDs')
                    by_id[key] = pred
                expected_keys = [(x['item_id'], x['revision_id']) for x in inputs]
                if set(by_id) != set(expected_keys):
                    raise ValueError('Pair prediction IDs do not match inputs')
                ordered_outputs = [by_id[k] for k in expected_keys]
                profile = profile_for(dataset['profile'])
                for output, request in zip(ordered_outputs, inputs):
                    self.validate_prediction(output, request, run, profile)
                pair_outputs = ordered_outputs
                model_input_equal = pair_result['model_input_equal']
            except Exception:
                error_code = 'INVALID_PAIR_RESULT'

        with self.store.tx() as c:
            self.store.cleanup_expired_in_tx(c)
            live = self.valid_lease(c, job)
            if not live:
                return True
            exp_now = c.execute('SELECT * FROM sensitivity_experiments WHERE job_id=?', (job['id'],)).fetchone()
            if not exp_now:
                return True
            if live['cancel_requested']:
                self.finish(c, job, 'cancelled')
                return True
            context_now = json.loads(exp_now['context_json'])
            if context_now.get('source_kind') == 'quick':
                from services.storage.db import DomainError
                try:
                    self.store.validate_quick_source(c, context_now['source_job_id'], context_now['source']['prediction_id'])
                except DomainError:
                    self._fail_sensitivity_tx(c, job, run, context_now, 'SOURCE_CONTEXT_CHANGED')
                    return True
            if error_code is not None:
                self._fail_sensitivity_tx(c, job, run, context_now, error_code)
                return True
            stamp = now()
            for n, request in enumerate(inputs):
                c.execute(
                    'INSERT INTO predictions VALUES(?,?,?,?,?,?)',
                    (uid(), run['id'], request['item_id'], request['revision_id'], encode(pair_outputs[n]), stamp),
                )
            context_now['attempt'] = {'error_code': None, 'model_input_equal': model_input_equal}
            c.execute('UPDATE sensitivity_experiments SET context_json=? WHERE job_id=?', (encode(context_now), job['id']))
            c.execute('UPDATE run_items SET error=NULL WHERE run_id=?', (run['id'],))
            c.execute('UPDATE jobs SET completed=2,failed=0,heartbeat_at=?,updated_at=? WHERE id=?', (stamp, stamp, job['id']))
            c.execute('UPDATE runs SET completed=2,failed=0 WHERE id=?', (run['id'],))
            self.finish(c, job, 'completed')
        return True

    def _run_attribution_once(self, attr_job):
        from services.attribution_contract import METHOD, signature, check_vectors, check_parity
        from services.attribution import (align_and_group, generate_permutations,
            evaluate_coalition_outputs, target_value, compute_shapley_from_coalition_map)
        from services.storage.db import DomainError

        def finish(status, code, message):
            with self.store.tx() as c:
                if self.valid_attribution_lease(c, attr_job):
                    self.finish_attribution(c, attr_job, status, code, message)
            return True

        try:
            with self.store.tx() as c:
                live = self.valid_attribution_lease(c, attr_job)
                if not live:
                    return True
                if live['cancel_requested']:
                    self.finish_attribution(c, attr_job, 'cancelled')
                    return True
                if live['compute_deadline'] <= time.time():
                    self.finish_attribution(c, attr_job, 'failed', 'COMPUTE_TIMEOUT', 'Phân tích từ ngữ quá thời gian. Thử lại.')
                    return True
                source_info, source = self.store._attribution_source(c, attr_job['source_job_id'], attr_job['source_prediction_id'])
                if not live['source_json'] or json.loads(live['source_json']) != source:
                    raise ValueError('Frozen source changed')
            profile_id = source['profile_id']
            profile = profile_for(profile_id)
            model, tokenizer, preprocessor, actual, manifest = self.registry.get_loaded_bundle(profile_id)
            if actual != source['execution_identity']:
                return finish('failed', 'MODEL_IDENTITY_CHANGED', 'Model đã đổi. Phân tích lại câu.')
            if preprocessor is not None and preprocessor.spec.get('kind') != 'underthesea_word_tokenize':
                return finish('unsupported', 'PROFILE_UNSUPPORTED', 'Profile chưa hỗ trợ ánh xạ từ ngữ.')
            try:
                alignment = align_and_group(source_info['item']['text'], tokenizer, preprocessor=preprocessor,
                    max_length=manifest.get('preprocessing', {}).get('max_length', 128))
            except ValueError:
                return finish('unsupported', 'MAPPING_FAILED', 'Chưa ánh xạ chắc chắn các cụm từ trong câu này.')
            if alignment['truncated']:
                return finish('unsupported', 'INPUT_TRUNCATED', 'Văn bản vượt quá giới hạn token; phân tích câu ngắn hơn để xem từ ngữ.')
            groups, full_input_ids = alignment['groups'], alignment['full_input_ids']
            if not groups or len(groups) > 24:
                return finish('unsupported', 'GROUP_LIMIT', 'Câu cần từ 1 đến 24 nhóm từ để phân tích tương tác.')
            target = json.loads(attr_job['target_json'])
            permutations, coalitions = generate_permutations(len(groups), permutations_count=METHOD['requested_permutations'], seed=METHOD['seed'])
            checkpoint = dict(signature=signature(dict(source=source, ids=full_input_ids, groups=groups, method=METHOD, target=target)))
            with self.store.tx() as c:
                live = self.valid_attribution_lease(c, attr_job)
                if not live:
                    return True
                if live['checkpoint_json'] and json.loads(live['checkpoint_json']) != checkpoint:
                    raise ValueError('Checkpoint identity changed')
                c.execute('UPDATE attribution_jobs SET checkpoint_json=? WHERE id=?', (encode(checkpoint), attr_job['id']))
                rows = c.execute('SELECT * FROM attribution_coalitions WHERE job_id=?', (attr_job['id'],)).fetchall()
            values = {r['coalition_mask']: float(r['val']) for r in rows}
            outputs = {r['coalition_mask']: json.loads(r['outputs_json']) for r in rows if r['outputs_json']}
            def mask(coalition):
                return ','.join(map(str, sorted(coalition)))
            if set(values) != set(outputs):
                raise ValueError('Legacy checkpoint lacks vector evidence')
            for key, output in outputs.items():
                check_vectors(output, profile)
                if not math.isfinite(values[key]) or abs(values[key]-target_value(output['sentiment'],target,profile)) > 1e-9:
                    raise ValueError('Checkpoint target differs from its vector evidence')
            pending = [x for x in coalitions if mask(x) not in values]
            batch = pending[:self.batch_size]
            if batch:
                batch_outputs = evaluate_coalition_outputs(model, full_input_ids, groups, batch, tokenizer=tokenizer)
                if len(batch_outputs) != len(batch):
                    raise ValueError('Coalition count mismatch')
                for coalition, output in zip(batch, batch_outputs):
                    check_vectors(output, profile)
                    val = target_value(output['sentiment'], target, profile)
                    if not math.isfinite(val):
                        raise ValueError('Nonfinite target')
                    outputs[mask(coalition)] = output
                    values[mask(coalition)] = val
            # Check the actual active bundle after forward, never synthesize it from run metadata.
            if self.registry.execution_identity(profile_id) != source['execution_identity']:
                return finish('failed', 'MODEL_IDENTITY_CHANGED', 'Model đã đổi. Phân tích lại câu.')
            full_mask = mask(frozenset(range(len(groups))))
            if full_mask in outputs:
                try:
                    check_parity(outputs[full_mask], source_info['item']['prediction'], profile)
                except ValueError:
                    return finish('failed', 'PREDICTION_MISMATCH', 'Điểm từ ngữ không khớp dự đoán nguồn. Phân tích lại câu.')
            with self.store.tx() as c:
                live = self.valid_attribution_lease(c, attr_job)
                if not live:
                    return True
                if live['compute_deadline'] <= time.time():
                    self.finish_attribution(c, attr_job, 'failed', 'COMPUTE_TIMEOUT', 'Phân tích từ ngữ quá thời gian. Thử lại.')
                    return True
                _, current = self.store._attribution_source(c, attr_job['source_job_id'], attr_job['source_prediction_id'])
                if current != source:
                    raise ValueError('Source changed before batch publication')
                for coalition in batch:
                    key = mask(coalition)
                    c.execute('INSERT OR IGNORE INTO attribution_coalitions(job_id,coalition_mask,val,outputs_json) VALUES(?,?,?,?)',
                              (attr_job['id'],key,values[key],encode(outputs[key])))
                completed = c.execute('SELECT COUNT(*) FROM attribution_coalitions WHERE job_id=?', (attr_job['id'],)).fetchone()[0]
                if completed < len(coalitions):
                    c.execute("UPDATE attribution_jobs SET progress_completed=?,progress_total=?,status='queued',lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?",
                              (completed,len(coalitions),now(),attr_job['id']))
                    return True
            result = compute_shapley_from_coalition_map(groups, permutations, {x:values[mask(x)] for x in coalitions})
            if (not all(math.isfinite(result[k]) for k in ('baseline_value','total_contribution','target_output','additivity_residual'))
                    or result['additivity_residual'] > 1e-6):
                raise ValueError('Invalid additivity')
            method = dict(METHOD, target=target, completed_permutations=len(permutations), evaluated_coalitions=len(coalitions))
            coverage = dict(truncated=False, input_token_count=len(full_input_ids), mapping_status='exact',
                analyzed_spans=len(groups), fixed_token_policy='special_tokens_only',
                explained_token_indices=[i for g in groups for i in g['token_indices']])
            aggregate = {k:result[k] for k in ('baseline_value','total_contribution','target_output','additivity_residual')}
            if self.registry.execution_identity(profile_id) != source['execution_identity']:
                return finish('failed', 'MODEL_IDENTITY_CHANGED', 'Model đã đổi. Phân tích lại câu.')
            with self.store.tx() as c:
                live = self.valid_attribution_lease(c, attr_job)
                if not live:
                    return True
                _, current = self.store._attribution_source(c, attr_job['source_job_id'], attr_job['source_prediction_id'])
                if current != source:
                    raise ValueError('Source changed before completion')
                if live['compute_deadline'] <= time.time():
                    self.finish_attribution(c, attr_job, 'failed', 'COMPUTE_TIMEOUT', 'Phân tích từ ngữ quá thời gian. Thử lại.')
                    return True
                c.execute("""UPDATE attribution_jobs SET status='completed',groups_json=?,aggregate_json=?,method_json=?,coverage_json=?,
                    progress_completed=?,progress_total=?,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?""",
                    (encode(result['groups']),encode(aggregate),encode(method),encode(coverage),len(coalitions),len(coalitions),now(),attr_job['id']))
                self.store._bound_attribution_cache(c)
        except DomainError:
            return finish('failed', 'SOURCE_CONTEXT_CHANGED', 'Nguồn đã thay đổi hoặc hết hạn. Phân tích lại câu.')
        except Exception:
            return finish('failed', 'INVALID_ATTRIBUTION', 'Không thể xác minh kết quả từ ngữ. Thử lại hoặc phân tích lại câu.')
        return True

    def run_once(self):
        """Process at most one microbatch, allowing quick jobs to preempt between batches."""
        self.heartbeat()
        self.cleanup_if_due()
        job = self.claim()
        if not job:
            attr_job = self.claim_attribution()
            if attr_job:
                with self.keepalive(attr_job):
                    return self._run_attribution_once(attr_job)
            from services.network_jobs import run_once as run_network_once
            return run_network_once(self.store)
        with self.keepalive(job):
            is_sensitivity = False
            sens_inputs = None
            sens_expected_identity = None
            sens_exp = None
            with self.store.tx() as c:
                live = self.valid_lease(c,job)
                if not live: return True
                if live['cancel_requested']:
                    self.finish(c,job,'cancelled'); return True
                run = self.store.run(job['run_id'],c)
                dataset = self.store.require_dataset(c,run['dataset_id'])
                sens_exp = c.execute('SELECT * FROM sensitivity_experiments WHERE job_id=?', (job['id'],)).fetchone()
                if sens_exp is not None:
                    is_sensitivity = True
                    context = json.loads(sens_exp['context_json'])
                    sens_expected_identity = context['execution']
                    existing_preds = c.execute('SELECT COUNT(*) FROM predictions WHERE run_id=?', (run['id'],)).fetchone()[0]
                    rows = c.execute(
                        '''SELECT ri.item_id, ri.revision_id, r.text, ri.error
                           FROM run_items ri
                           JOIN items i ON i.id=ri.item_id
                           JOIN revisions r ON r.id=ri.revision_id
                           WHERE ri.run_id=?
                           ORDER BY i.source_row ASC''',
                        (run['id'],),
                    ).fetchall()
                    expected_ids = [sens_exp['baseline_item_id'], sens_exp['variant_item_id']]
                    if (
                        existing_preds != 0
                        or len(rows) != 2
                        or [r['item_id'] for r in rows] != expected_ids
                        or any(r['error'] is not None for r in rows)
                    ):
                        self._fail_sensitivity_tx(c, job, run, context, 'INVALID_PAIR_RESULT')
                        return True
                    sens_inputs = [{'item_id': r['item_id'], 'revision_id': r['revision_id'], 'text': r['text']} for r in rows]
                    c.execute("UPDATE jobs SET status='running' WHERE id=?", (job['id'],))
                    c.execute("UPDATE runs SET status='running' WHERE id=?", (run['id'],))
                else:
                    rows = c.execute('SELECT ri.item_id,ri.revision_id,r.text FROM run_items ri JOIN revisions r ON r.id=ri.revision_id WHERE ri.run_id=? AND ri.error IS NULL AND NOT EXISTS(SELECT 1 FROM predictions p WHERE p.run_id=ri.run_id AND p.item_id=ri.item_id) ORDER BY (SELECT source_row FROM items WHERE id=ri.item_id) LIMIT ?', (run['id'],self.batch_size)).fetchall()
                    inputs = [dict(r) for r in rows]
                    c.execute("UPDATE jobs SET status='running' WHERE id=?",(job['id'],))
                    c.execute("UPDATE runs SET status='running' WHERE id=?",(run['id'],))
            if is_sensitivity:
                return self._run_sensitivity_once(job, run, dataset, sens_exp, sens_inputs, sens_expected_identity)
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
