"""Read-snapshot identity for aggregate/drill-down consistency.

Tokens contain no text and are computed in the same short SQLite read transaction
as the response. They conservatively invalidate when any dataset input, review,
prediction or run changes; a run id alone cannot freeze effective labels.
"""
import hashlib
import json

from services.storage.db import DomainError


def scope_token(store, connection, dataset_id, filters):
    dataset = store.require_dataset(connection, dataset_id)
    snapshot = store.run_snapshot(dataset_id, filters, connection)
    identity = [dict(dataset), snapshot, filters.get('label_source', 'effective')]
    queries = [
        ('SELECT * FROM items WHERE dataset_id=? ORDER BY id',),
        ('SELECT r.* FROM revisions r JOIN items i ON i.id=r.item_id WHERE i.dataset_id=? ORDER BY r.id',),
        ('SELECT r.* FROM reviews r JOIN items i ON i.id=r.item_id WHERE i.dataset_id=? ORDER BY r.id',),
        ('SELECT * FROM runs WHERE dataset_id=? ORDER BY id',),
        ('SELECT r.* FROM run_items r JOIN runs n ON n.id=r.run_id WHERE n.dataset_id=? ORDER BY r.run_id,r.item_id',),
        ('SELECT p.* FROM predictions p JOIN items i ON i.id=p.item_id WHERE i.dataset_id=? ORDER BY p.id',),
    ]
    for (sql,) in queries:
        identity.append([dict(row) for row in connection.execute(sql, (dataset_id,))])
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def scoped_response(store, dataset_id, filters, *, page=None, page_size=25,
                    expected_token=None, expected_run_id=None):
    with store.connect() as connection:
        connection.execute('BEGIN')
        token = scope_token(store, connection, dataset_id, filters)
        snapshot = store.run_snapshot(dataset_id, filters, connection)
        if ((expected_token is not None and expected_token != token)
                or (expected_run_id is not None and expected_run_id != (snapshot['resolved_run_id'] or ''))):
            raise DomainError('SCOPE_CHANGED', 'Dữ liệu hoặc nhãn đã đổi. Tải lại thống kê trước khi xem phản hồi.', 409)
        result = (store.summary(dataset_id, filters, connection) if page is None
                  else store.items_page(dataset_id, filters, page, page_size, connection))
        return dict(result, scope_token=token, dataset_id=dataset_id,
                    label_source=filters.get('label_source', 'effective'))
