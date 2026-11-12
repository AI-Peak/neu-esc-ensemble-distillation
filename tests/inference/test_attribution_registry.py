"""Identity/publication race regressions using software doubles, never an encoder."""
import json
import time
import uuid

import pytest

from services.storage.db import DomainError
from services.worker import Worker
from tests.support import TestOnlyRegistry


@pytest.fixture
def source(tmp_path):
    registry = TestOnlyRegistry()
    worker = Worker(tmp_path, registry, batch_size=8)
    store = worker.store
    dataset = store.create_dataset(dict(name='Authored software fixture', profile='neu',
        items=[dict(text='Tốt', metadata={'_temporary_source': 'quick-analysis-v1'})]), temporary=True)
    run = store.create_run(dataset['id'], registry.status('neu'))
    worker.run_once()
    item = store.job(run['job_id'])['result']
    prediction = item['prediction']
    def create(resolver=None):
        return store.create_attribution_job(run['job_id'], prediction['id'],
            {'kind': 'polarity_margin'}, str(uuid.uuid4()), execution_resolver=resolver or registry.execution_identity)
    return store, worker, registry, dataset, run, item, create


@pytest.mark.parametrize('mutation', ['edit', 'expiry', 'delete'])
def test_get_rechecks_source_after_execution_inspection(source, mutation):
    store, worker, registry, dataset, run, item, create = source
    handle = create()['attribution_id']
    worker.run_once()
    assert store.get_attribution(handle)['status'] == 'completed'
    def inspect_and_mutate(profile):
        identity = registry.execution_identity(profile)
        if mutation == 'edit':
            store.edit_text(item['id'], 'Nội dung vừa thay đổi.', 1)
        elif mutation == 'delete':
            store.delete_dataset(dataset['id'])
        else:
            with store.tx() as connection:
                connection.execute('UPDATE datasets SET expires_at=? WHERE id=?', (time.time() - 1, dataset['id']))
        return identity
    with pytest.raises(DomainError):
        store.get_attribution(handle, execution_resolver=inspect_and_mutate)


@pytest.mark.parametrize('mutation', ['edit', 'expiry', 'delete', 'model', 'cancel'])
def test_worker_does_not_publish_after_mutation_during_forward(source, mutation):
    store, worker, registry, dataset, run, item, create = source
    handle = create()['attribution_id']
    original = registry.get_loaded_bundle
    def bundle(profile):
        model, tokenizer, preprocessor, identity, manifest = original(profile)
        class Forward:
            def __call__(self, input_ids, attention_mask):
                outputs = model(input_ids, attention_mask)
                if mutation == 'edit':
                    store.edit_text(item['id'], 'Nội dung vừa thay đổi.', 1)
                elif mutation == 'delete':
                    store.delete_dataset(dataset['id'])
                elif mutation == 'expiry':
                    with store.tx() as connection:
                        connection.execute('UPDATE datasets SET expires_at=? WHERE id=?', (time.time() - 1, dataset['id']))
                elif mutation == 'model':
                    registry.manifest_sha256 = 'f' * 64
                else:
                    store.cancel_attribution(handle)
                return outputs
        return Forward(), tokenizer, preprocessor, identity, manifest
    registry.get_loaded_bundle = bundle
    assert worker.run_once()
    with store.connect() as connection:
        row = connection.execute('SELECT status,error_code FROM attribution_jobs WHERE id=?', (handle,)).fetchone()
        if mutation == 'delete':
            assert row is None
        else:
            assert row['status'] in ('failed', 'cancelled')
            assert row['error_code'] == ('MODEL_IDENTITY_CHANGED' if mutation == 'model' else
                                         None if mutation == 'cancel' else 'SOURCE_CONTEXT_CHANGED')
        assert connection.execute('SELECT COUNT(*) FROM attribution_coalitions WHERE job_id=?', (handle,)).fetchone()[0] == 0


def test_compute_deadline_expiring_inside_forward_prevents_batch_commit(source):
    store, worker, registry, dataset, run, item, create = source
    handle = create()['attribution_id']
    original = registry.get_loaded_bundle
    def bundle(profile):
        model, tokenizer, preprocessor, identity, manifest = original(profile)
        class Forward:
            def __call__(self, input_ids, attention_mask):
                outputs = model(input_ids, attention_mask)
                with store.tx() as connection:
                    connection.execute('UPDATE attribution_jobs SET compute_deadline=? WHERE id=?', (time.time() - 1, handle))
                return outputs
        return Forward(), tokenizer, preprocessor, identity, manifest
    registry.get_loaded_bundle = bundle
    assert worker.run_once()
    with store.connect() as connection:
        row = connection.execute('SELECT status,error_code FROM attribution_jobs WHERE id=?', (handle,)).fetchone()
        assert row['status'] == 'failed' and row['error_code'] == 'COMPUTE_TIMEOUT'
        assert connection.execute('SELECT COUNT(*) FROM attribution_coalitions WHERE job_id=?', (handle,)).fetchone()[0] == 0


@pytest.mark.parametrize('threads, expected', [(1, 1), (2, 2), (16, 4)])
def test_inference_loader_caps_default_threads_before_model_loading(tmp_path, monkeypatch, threads, expected):
    import torch
    from transformers import AutoConfig
    from services.inference.registry import load_artifact
    captured = []
    monkeypatch.setattr(torch, 'get_num_threads', lambda: threads)
    monkeypatch.setattr(torch, 'set_num_threads', captured.append)
    class StopBeforeLoading(RuntimeError):
        pass
    def stop(*args, **kwargs):
        raise StopBeforeLoading()
    monkeypatch.setattr(AutoConfig, 'from_pretrained', stop)
    with pytest.raises(StopBeforeLoading):
        load_artifact(tmp_path, {'format_version': 2})
    assert captured == [expected]
