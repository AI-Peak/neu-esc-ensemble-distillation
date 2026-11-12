"""Independent review regressions: bounded cache, immutable sources and scheduling.

All forward calls use the explicit software score game; this is not model evidence.
"""
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

import pytest

from scripts.backup_local import backup, restore
from services.storage.db import DomainError, MIGRATION_2, MIGRATION_3, Store
from services.worker import Worker
from tests.support import TestOnlyRegistry
from tests.test_backup import _build_v1_database


@pytest.fixture
def ctx(tmp_path):
    registry = TestOnlyRegistry()
    worker = Worker(tmp_path, registry, batch_size=2)
    store = worker.store

    def source(text='Wifi thư viện hơi chậm nhưng nhân viên hỗ trợ tốt.'):
        dataset = store.create_dataset(dict(name='Quick test-only source', profile='neu',
            items=[dict(text=text, metadata={'_temporary_source': 'quick-analysis-v1'})]), temporary=True)
        run = store.create_run(dataset['id'], registry.status('neu'))
        assert worker.run_once()
        item = store.job(run['job_id'])['result']
        return dataset, run, item

    return store, worker, registry, source


def create(store, registry, run, item, *, key=None, target=None):
    return store.create_attribution_job(run['job_id'], item['prediction']['id'],
        target or {'kind': 'polarity_margin'}, key or str(uuid4()),
        execution_resolver=registry.execution_identity)


def drain(store, worker, handle):
    for _ in range(120):
        result = store.get_attribution(handle)
        if result['status'] not in ('queued', 'running'):
            return result
        worker.run_once()
    raise AssertionError('Software attribution did not terminate')


def test_cache_caps_reusable_successes_preserves_independent_handles_and_source_ttl(ctx):
    store, worker, registry, source = ctx
    dataset, run, item = source('Tốt')
    # Shortening source lifetime must bound cache, never be extended by reads/hits.
    source_expiry = time.time() + 120
    with store.tx() as c:
        c.execute('UPDATE datasets SET expires_at=? WHERE id=?', (source_expiry, dataset['id']))
    original = create(store, registry, run, item)['attribution_id']
    assert drain(store, worker, original)['status'] == 'completed'
    handles = [original]
    for _ in range(102):
        cached = create(store, registry, run, item)
        assert cached['status'] == 'completed'
        handles.append(cached['attribution_id'])
    assert len(set(handles)) == 103
    with store.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM attribution_jobs WHERE cache_key IS NOT NULL AND status='completed'").fetchone()[0] == 100
        assert c.execute('SELECT COUNT(*) FROM attribution_jobs').fetchone()[0] == 103
        assert c.execute('SELECT MAX(expires_at) FROM attribution_jobs').fetchone()[0] <= source_expiry
        assert c.execute('SELECT expires_at FROM datasets WHERE id=?', (dataset['id'],)).fetchone()[0] == source_expiry
    # Cache eviction does not invalidate another tab's completed result/handle.
    assert store.cancel_attribution(handles[0])['status'] == 'completed'
    assert store.get_attribution(handles[-1])['status'] == 'completed'


def test_cache_hit_key_cannot_rebind_to_another_source_and_expired_cache_is_not_reused(ctx):
    store, worker, registry, source = ctx
    dataset, run, item = source('Tốt')
    original = create(store, registry, run, item)['attribution_id']
    assert drain(store, worker, original)['status'] == 'completed'
    key = str(uuid4())
    hit = create(store, registry, run, item, key=key)
    _, other_run, other_item = source('Chậm')
    with pytest.raises(DomainError) as conflict:
        create(store, registry, other_run, other_item, key=key)
    assert conflict.value.status == 409
    assert store.get_attribution(hit['attribution_id'])['source']['source_job_id'] == run['job_id']
    with store.tx() as c:
        c.execute('UPDATE attribution_jobs SET expires_at=? WHERE source_job_id=?', (time.time()-1, run['job_id']))
    fresh = create(store, registry, run, item)
    assert fresh['status'] == 'queued' and fresh['attribution_id'] not in {original, hit['attribution_id']}
    with store.tx() as c:
        c.execute('UPDATE datasets SET expires_at=? WHERE id=?', (time.time()-1, dataset['id']))
    with pytest.raises(DomainError) as gone:
        create(store, registry, run, item)
    assert gone.value.status == 410


def test_attribution_does_not_modify_source_prediction_dataset_counts_or_export_bytes(ctx):
    store, worker, registry, source = ctx
    durable = store.create_dataset(dict(name='Durable counter fixture', profile='neu', items=[dict(text='Phản hồi bền.')]))
    export = store.export(durable['id'], {})
    export_before = store.export_bytes(export['id'])
    _, run, item = source()
    source_before = store.job(run['job_id'])
    summary_before = store.summary(durable['id'], {})
    datasets_before = store.datasets()
    with store.connect() as c:
        counts_before = [c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                         for table in ('datasets','items','runs','jobs','predictions','exports')]
    handle = create(store, registry, run, item)['attribution_id']
    assert drain(store, worker, handle)['status'] == 'completed'
    assert store.job(run['job_id']) == source_before
    assert store.summary(durable['id'], {}) == summary_before
    assert store.datasets() == datasets_before
    assert store.export_bytes(export['id']) == export_before
    with store.connect() as c:
        assert [c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                for table in ('datasets','items','runs','jobs','predictions','exports')] == counts_before


def test_quick_prediction_preempts_the_next_attribution_microbatch(ctx):
    store, worker, registry, source = ctx
    _, run, item = source()
    handle = create(store, registry, run, item)['attribution_id']
    assert worker.run_once()
    with store.connect() as c:
        before = dict(c.execute('SELECT * FROM attribution_jobs WHERE id=?', (handle,)).fetchone())
    assert before['status'] == 'queued' and 0 < before['progress_completed'] < before['progress_total']
    quick_ds = store.create_dataset(dict(name='New priority prediction', profile='neu',
        items=[dict(text='Câu mới được xử lý giữa các batch.', metadata={'_temporary_source': 'quick-analysis-v1'})]), temporary=True)
    quick_run = store.create_run(quick_ds['id'], registry.status('neu'))
    assert worker.run_once()
    assert store.job(quick_run['job_id'])['status'] == 'completed'
    with store.connect() as c:
        after = dict(c.execute('SELECT * FROM attribution_jobs WHERE id=?', (handle,)).fetchone())
    assert after['progress_completed'] == before['progress_completed']
    assert after['compute_deadline'] == before['compute_deadline']
    assert drain(store, worker, handle)['status'] == 'completed'


def test_upgrade_v3_and_backup_keep_durable_exports_but_remove_quick_attribution(ctx, tmp_path):
    runtime = tmp_path / 'v3-runtime'
    original = _build_v1_database(runtime)
    # Construct the previously applied migrations exactly; Store must add v4.
    with sqlite3.connect(runtime / 'workspace.sqlite3') as c:
        for version, sql in ((2, MIGRATION_2), (3, MIGRATION_3)):
            for statement in sql.split(';'):
                if statement.strip():
                    c.execute(statement)
            c.execute('INSERT INTO schema_migrations VALUES(?,?)', (version, '2026-11-12T00:00:00Z'))
    store = Store(runtime)
    assert store.database_version() == 4
    assert store.export_bytes(original['export_id']) == original['v1_csv_bytes']
    registry = TestOnlyRegistry()
    worker = Worker(runtime, registry)
    dataset = store.create_dataset(dict(name='Temporary source', profile='neu',
        items=[dict(text='PRIVATE_QUICK_FIXTURE', metadata={'_temporary_source': 'quick-analysis-v1'})]), temporary=True)
    run = store.create_run(dataset['id'], registry.status('neu'))
    worker.run_once()
    item = store.job(run['job_id'])['result']
    create(store, registry, run, item)
    archive = tmp_path / 'v4-backup.zip'
    backup(runtime, archive)
    destination = tmp_path / 'restored'
    restore(archive, destination)
    restored = Store(destination)
    assert restored.database_version() == 4
    assert restored.export_bytes(original['export_id']) == original['v1_csv_bytes']
    assert len(restored.items_page(original['dataset_id'], {}, 1, 25)['items']) == 2
    with restored.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM attribution_jobs').fetchone()[0] == 0
        assert c.execute('SELECT COUNT(*) FROM attribution_coalitions').fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM idempotency WHERE operation='attribution'").fetchone()[0] == 0
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []
    assert b'PRIVATE_QUICK_FIXTURE' not in (destination / 'workspace.sqlite3').read_bytes()
