"""Bounded dataset network snapshots; NLP runs only in the worker."""
import json
import time

from services.analytics import selected_labels
from services.attribution_contract import signature
from services.demo_scope import scope_token
from services.storage.db import DomainError, encode, now, profile_for, uid

VERSION = 'cooccurrence-v2'
PARAMS = dict(window_size=5, max_nodes=40, max_edges=120, min_df=1,
              max_distance=4,window_unit='segmented_token_positions',
              sentence_boundaries='punctuation_or_linebreak',
              community_method='connected_components',stopwords_version='v2',layout_method='deterministic_sunflower_v2')


def normalized_filters(filters):
    defaults = dict(run_id=None,label_source='effective',q=None,sentiment=None,topic=None,
                    review_status='all',review_signal='all',sort='source_row',direction='asc')
    defaults.update({k:v for k,v in filters.items() if v not in (None, '')})
    if 'item_ids' in defaults:
        defaults['item_ids'] = ','.join(sorted(set(defaults['item_ids'].split(','))))
    return defaults


def response(row):
    data = json.loads(row['result_json']) if row['result_json'] else dict(nodes=[],edges=[],communities=[],
        total_nodes=0,total_edges=0,source_item_count=0)
    return dict(data,network_id=row['id'],dataset_id=row['dataset_id'],scope_token=row['scope_token'],
                filter_signature=row['filter_signature'],network_version=VERSION,params=PARAMS,
                status=row['status'],label_source=json.loads(row['filters_json'])['label_source'],
                scope_item_count=json.loads(row['snapshot_json'])['scope_item_count'],
                error=dict(code=row['error_code'],message='Dữ liệu đã đổi. Tải lại mạng từ.') if row['error_code'] else None)


def request_network(store, dataset_id, filters):
    filters = normalized_filters(filters)
    filter_id = signature(dict(filters=filters,version=VERSION,params=PARAMS))
    # Snapshot/copy only, with no segmenter imported or NLP work under SQLite locks.
    with store.tx() as c:
        token = scope_token(store,c,dataset_id,filters)
        cached = c.execute("SELECT * FROM network_jobs WHERE dataset_id=? AND scope_token=? AND filter_signature=? AND expires_at>? AND status IN ('queued','running','completed') ORDER BY created_at DESC LIMIT 1",
                           (dataset_id,token,filter_id,time.time())).fetchone()
        if cached:
            return response(cached)
        if c.execute("SELECT COUNT(*) FROM network_jobs WHERE status IN ('queued','running')").fetchone()[0] >= 10:
            raise DomainError('NETWORK_BUSY','Hàng đợi mạng từ đang đầy. Thử lại sau.',429)
        rows = store.query_items(dataset_id,filters,c)
        profile = profile_for(store.require_dataset(c,dataset_id)['profile'])
        valid_ids = {label['id'] for label in profile['sentiment']}
        population = [dict(id=row['id'],text=row['text']) for row in rows
                      if selected_labels(row,filters['label_source'])['sentiment'] in valid_ids]
        network_id = uid()
        snapshot = dict(items=population,scope_item_count=len(rows))
        c.execute('INSERT INTO network_jobs(id,dataset_id,scope_token,filter_signature,filters_json,snapshot_json,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?)',
                  (network_id,dataset_id,token,filter_id,encode(filters),encode(snapshot),'queued',now(),time.time()+900))
        c.execute("DELETE FROM network_jobs WHERE status NOT IN ('queued','running') AND id IN (SELECT id FROM network_jobs ORDER BY created_at DESC,rowid DESC LIMIT -1 OFFSET 100)")
        return response(c.execute('SELECT * FROM network_jobs WHERE id=?',(network_id,)).fetchone())


def evidence(store, network_id, selection_type, selection_id, page, page_size):
    with store.connect() as c:
        c.execute('BEGIN')
        row = c.execute('SELECT * FROM network_jobs WHERE id=?',(network_id,)).fetchone()
        if not row:
            raise DomainError('NOT_FOUND','Mạng từ không còn tồn tại. Tải lại mạng từ.',404)
        if row['expires_at'] <= time.time():
            raise DomainError('NETWORK_EXPIRED','Mạng từ đã hết hạn. Tải lại mạng từ.',410)
        filters = json.loads(row['filters_json'])
        token = scope_token(store,c,row['dataset_id'],filters)
        if token != row['scope_token']:
            raise DomainError('SCOPE_CHANGED','Dữ liệu hoặc nhãn đã đổi. Tải lại mạng từ.',409)
        if row['status'] != 'completed':
            raise DomainError('NETWORK_NOT_READY','Mạng từ chưa sẵn sàng.',409)
        data = json.loads(row['result_json'])
        collection = {'node':'nodes','edge':'edges','community':'communities'}.get(selection_type)
        if collection is None:
            raise DomainError('INVALID_SELECTION','Lựa chọn mạng từ không hợp lệ.',422)
        selection = next((x for x in data[collection] if str(x['id']) == selection_id),None)
        if selection is None:
            raise DomainError('INVALID_SELECTION','Không tìm thấy từ hoặc quan hệ trong mạng này.',422)
        ids = set(selection['item_ids'])
        # Resolve membership from the server-owned immutable graph, never client IDs.
        rows = [r for r in store.query_items(row['dataset_id'],filters,c) if r['id'] in ids]
        start = (page-1)*page_size
        snapshot=store.run_snapshot(row['dataset_id'],filters,c)
        return dict(items=rows[start:start+page_size],total=len(rows),page=page,page_size=page_size,
                    scope_token=token,network_id=network_id,filter_signature=row['filter_signature'],
                    dataset_id=row['dataset_id'],label_source=filters['label_source'],**snapshot)


def run_once(store):
    with store.tx() as c:
        row = c.execute("SELECT * FROM network_jobs WHERE status IN ('queued','running') AND expires_at>? ORDER BY created_at LIMIT 1",(time.time(),)).fetchone()
        if not row:
            return False
        job = dict(row)
        c.execute("UPDATE network_jobs SET status='running' WHERE id=?",(job['id'],))
    from services.text_network import build_network
    try:
        snapshot = json.loads(job['snapshot_json'])
        result = build_network(snapshot['items'],max_nodes=40,min_df=1,window_size=5)
        error = None
    except Exception:
        result, error = None, 'NETWORK_FAILED'
    with store.tx() as c:
        live = c.execute('SELECT * FROM network_jobs WHERE id=?',(job['id'],)).fetchone()
        if not live or live['expires_at'] <= time.time():
            return True
        filters = json.loads(job['filters_json'])
        if scope_token(store,c,job['dataset_id'],filters) != job['scope_token']:
            error = 'SCOPE_CHANGED'
        c.execute('UPDATE network_jobs SET status=?,result_json=?,error_code=? WHERE id=?',
                  ('failed' if error else 'completed',encode(result) if not error else None,error,job['id']))
    return True
