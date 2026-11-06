import csv
import hashlib
import io
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILES = json.loads((ROOT / 'services/profiles.json').read_text(encoding='utf-8-sig'))
TERMINAL = {'completed', 'completed_with_errors', 'failed', 'cancelled', 'interrupted'}


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def uid():
    return str(uuid.uuid4())


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


class DomainError(Exception):
    def __init__(self, code, message, status=400, details=None):
        self.code, self.message, self.status, self.details = code, message, status, details
        super().__init__(message)


def profile_for(profile):
    for value in PROFILES:
        if value['id'] == profile:
            return value
    raise DomainError('INVALID_PROFILE', 'Loại nội dung không hợp lệ.', 422)


def check_text(text):
    if not isinstance(text, str) or not text.strip():
        raise DomainError('INVALID_TEXT', 'Nội dung không được để trống.', 422)
    if len(text) > 5000:
        raise DomainError('TEXT_TOO_LONG', 'Mỗi phản hồi tối đa 5.000 ký tự.', 422)
    return text


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()


MIGRATION_1 = '''
CREATE TABLE datasets(id TEXT PRIMARY KEY,name TEXT NOT NULL,profile TEXT NOT NULL,schema_id TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,temporary INTEGER NOT NULL DEFAULT 0,expires_at REAL);
CREATE TABLE items(id TEXT PRIMARY KEY,dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,source_row INTEGER NOT NULL,current_revision_id TEXT);
CREATE TABLE revisions(id TEXT PRIMARY KEY,item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,revision INTEGER NOT NULL,text TEXT NOT NULL,text_hash TEXT NOT NULL,metadata_json TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(item_id,revision));
CREATE TABLE reference_labels(revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,task TEXT NOT NULL,schema_id TEXT NOT NULL,label_id INTEGER NOT NULL,source TEXT NOT NULL,PRIMARY KEY(revision_id,task));
CREATE TABLE runs(id TEXT PRIMARY KEY,dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,schema_id TEXT NOT NULL,model_id TEXT NOT NULL,model_version TEXT NOT NULL,status TEXT NOT NULL,total INTEGER NOT NULL,completed INTEGER NOT NULL DEFAULT 0,failed INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE run_items(run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,error TEXT,PRIMARY KEY(run_id,item_id));
CREATE TABLE predictions(id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,payload TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(run_id,item_id,revision_id));
CREATE TABLE reviews(id TEXT PRIMARY KEY,item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,schema_id TEXT NOT NULL,task TEXT NOT NULL,review_revision INTEGER NOT NULL,status TEXT NOT NULL,label_id INTEGER,note TEXT NOT NULL,source_prediction_id TEXT,created_at TEXT NOT NULL,UNIQUE(revision_id,task,review_revision));
CREATE TABLE jobs(id TEXT PRIMARY KEY,run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,status TEXT NOT NULL,total INTEGER NOT NULL,completed INTEGER NOT NULL DEFAULT 0,failed INTEGER NOT NULL DEFAULT 0,cancel_requested INTEGER NOT NULL DEFAULT 0,error TEXT,attempt_id INTEGER NOT NULL DEFAULT 0,lease_owner TEXT,lease_expires_at REAL,heartbeat_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,priority INTEGER NOT NULL DEFAULT 0);
CREATE TABLE previews(id TEXT PRIMARY KEY,payload TEXT NOT NULL,expires_at REAL NOT NULL);
CREATE TABLE exports(id TEXT PRIMARY KEY,dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,run_id TEXT,filters TEXT NOT NULL,snapshot TEXT NOT NULL,csv_blob BLOB NOT NULL,row_count INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE idempotency(key TEXT NOT NULL,operation TEXT NOT NULL,request_hash TEXT NOT NULL,result_id TEXT NOT NULL,PRIMARY KEY(key,operation));
CREATE TABLE worker_status(id INTEGER PRIMARY KEY CHECK(id=1),owner TEXT NOT NULL,pid INTEGER NOT NULL,heartbeat_at TEXT NOT NULL,expires_at REAL NOT NULL);
CREATE INDEX revisions_item ON revisions(item_id,revision);
CREATE INDEX reviews_latest ON reviews(revision_id,task,review_revision DESC);
CREATE INDEX jobs_queue ON jobs(status,priority DESC,created_at);
CREATE INDEX predictions_revision ON predictions(revision_id,created_at DESC);
'''


class Store:
    def __init__(self, runtime_dir=None):
        self.runtime = Path(runtime_dir or os.environ.get('FEEDBACK_RUNTIME') or ROOT / 'runtime').resolve()
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.path = self.runtime / 'workspace.sqlite3'
        with self.connect() as conn:
            # journal_mode lock upgrades can fail immediately despite busy_timeout
            # when API and worker create a new database at the same instant.
            deadline = time.monotonic()+30
            while True:
                try:
                    conn.execute('PRAGMA journal_mode=WAL')
                    break
                except sqlite3.OperationalError as exc:
                    if 'locked' not in str(exc).lower() or time.monotonic() >= deadline: raise
                    time.sleep(.025)
            conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            conn.execute('BEGIN IMMEDIATE')
            if not conn.execute('SELECT 1 FROM schema_migrations WHERE version=1').fetchone():
                for statement in MIGRATION_1.split(';'):
                    if statement.strip(): conn.execute(statement)
                conn.execute('INSERT INTO schema_migrations VALUES(1,?)', (now(),))
            conn.commit()
        self.cleanup()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=30000')
        return conn

    @contextmanager
    def tx(self):
        conn = self.connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def cleanup(self):
        with self.tx() as c:
            self.recover(c)
            c.execute('DELETE FROM previews WHERE expires_at<?', (time.time(),))
            # A stale expiry marker must never revoke queued or live inference.
            c.execute("""DELETE FROM datasets WHERE temporary=1 AND expires_at IS NOT NULL AND expires_at<?
                         AND NOT EXISTS (SELECT 1 FROM runs r JOIN jobs j ON j.run_id=r.id
                             WHERE r.dataset_id=datasets.id AND j.status NOT IN
                             ('completed','completed_with_errors','failed','cancelled','interrupted'))""", (time.time(),))

    def recover(self, c):
        expired = c.execute("SELECT id,run_id FROM jobs WHERE status IN ('running','loading_model') AND lease_expires_at<?", (time.time(),)).fetchall()
        for j in expired:
            c.execute("UPDATE jobs SET status='interrupted',lease_owner=NULL,lease_expires_at=NULL,error='Worker lease expired',updated_at=? WHERE id=?", (now(), j['id']))
            c.execute("UPDATE runs SET status='interrupted' WHERE id=?", (j['run_id'],))
            self.expire_quick(c, j['run_id'])

    def expire_quick(self, c, run_id):
        c.execute('UPDATE datasets SET expires_at=? WHERE temporary=1 AND id=(SELECT dataset_id FROM runs WHERE id=?)', (time.time() + 900, run_id))

    def require_dataset(self, c, dataset_id):
        d = c.execute('SELECT * FROM datasets WHERE id=?', (dataset_id,)).fetchone()
        if not d:
            raise DomainError('NOT_FOUND', 'Không tìm thấy bộ phản hồi.', 404)
        return d

    def dataset(self, dataset_id, c=None):
        if c is None:
            with self.connect() as conn:
                conn.execute('BEGIN')
                return self.dataset(dataset_id, conn)
        d = dict(self.require_dataset(c, dataset_id))
        items = self.query_items(dataset_id, {}, c)
        d.update(item_count=len(items), processed_count=sum(bool(i['prediction']) for i in items), reviewed_count=sum(self.review_count(i) == 2 for i in items), partial_review_count=sum(self.review_count(i) == 1 for i in items))
        latest = c.execute('SELECT id FROM runs WHERE dataset_id=? ORDER BY created_at DESC LIMIT 1', (dataset_id,)).fetchone()
        d['latest_run_id'] = latest['id'] if latest else None
        d.pop('temporary'); d.pop('expires_at')
        return d

    def datasets(self):
        with self.connect() as c:
            c.execute('BEGIN')
            return [self.dataset(r['id'], c) for r in c.execute('SELECT id FROM datasets WHERE temporary=0 ORDER BY updated_at DESC')]

    def remember(self, c, key, operation, body, result_id=None):
        if not key:
            return None
        digest = hashlib.sha256(encode(body).encode()).hexdigest()
        prev = c.execute('SELECT * FROM idempotency WHERE key=? AND operation=?', (key, operation)).fetchone()
        if prev:
            if prev['request_hash'] != digest:
                raise DomainError('IDEMPOTENCY_CONFLICT', 'Khóa yêu cầu đã dùng với nội dung khác.', 409)
            return prev['result_id']
        if result_id:
            c.execute('INSERT INTO idempotency VALUES(?,?,?,?)', (key, operation, digest, result_id))
        return None

    def preview(self, data, delimiter=None):
        if len(data) > 5 * 1024 * 1024:
            raise DomainError('FILE_TOO_LARGE', 'CSV tối đa 5 MB.', 413)
        try:
            content = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise DomainError('INVALID_ENCODING', 'CSV phải dùng UTF-8.', 422)
        if delimiter is not None and delimiter not in [',', ';', '\t', '|']:
            raise DomainError('INVALID_DELIMITER', 'Dấu phân cách không được hỗ trợ.', 422)
        if not delimiter:
            try:
                delimiter = csv.Sniffer().sniff(content[:65536], delimiters=',;\t|').delimiter
            except csv.Error:
                delimiter = ','
        try:
            reader = csv.reader(io.StringIO(content, newline=''), delimiter=delimiter, strict=True)
            columns = next(reader)
            if not columns or any(not x.strip() for x in columns) or len(set(columns)) != len(columns):
                raise DomainError('INVALID_COLUMNS', 'Tên cột phải có nội dung và không trùng.', 422)
            rows, issues = [], []
            for rownum, row in enumerate(reader, 1):
                if len(rows) >= 500:
                    raise DomainError('TOO_MANY_ROWS', 'Mỗi bộ tối đa 500 phản hồi.', 422)
                if len(row) != len(columns):
                    issues.append(dict(row=rownum, code='COLUMN_COUNT', message='Số ô không khớp tiêu đề.'))
                rows.append(dict(zip(columns, row + [''] * (len(columns) - len(row)))))
        except (csv.Error, StopIteration) as exc:
            raise DomainError('INVALID_CSV', 'Không đọc được CSV.', 422, str(exc))
        seen = set()
        suggested = 'text' if 'text' in columns else columns[0]
        for n, row in enumerate(rows, 1):
            text = row.get(suggested, '')
            if not text.strip() or len(text) > 5000:
                issues.append(dict(row=n, code='INVALID_TEXT', message='Cột gợi ý trống hoặc quá 5.000 ký tự; kiểm lại cột đã chọn.'))
            if text in seen:
                issues.append(dict(row=n, code='DUPLICATE', message='Nội dung trùng; vẫn được giữ khi nhập.'))
            seen.add(text)
        result = dict(preview_id=uid(), columns=columns, rows=rows, total_rows=len(rows), delimiter=delimiter, issues=issues, expires_at=datetime.fromtimestamp(time.time() + 900, timezone.utc).isoformat())
        with self.tx() as c:
            c.execute('INSERT INTO previews VALUES(?,?,?)', (result['preview_id'], encode(result), time.time() + 900))
        return result

    def create_dataset(self, body, key=None, temporary=False):
        profile = profile_for(body.get('profile'))
        name = body.get('name', '').strip()
        if not name or len(name) > 200:
            raise DomainError('INVALID_NAME', 'Tên bộ phản hồi cần từ 1 đến 200 ký tự.', 422)
        with self.tx() as c:
            prior = self.remember(c, key, 'dataset', body)
            if prior:
                return self.dataset(prior, c)
            if bool(body.get('preview_id')) == (body.get('items') is not None):
                raise DomainError('INVALID_INPUT', 'Chọn CSV đã kiểm tra hoặc danh sách nội dung.', 422)
            reference = body.get('reference')
            if reference and not str(reference.get('source', '')).strip():
                raise DomainError('INVALID_REFERENCE', 'Cần xác nhận nguồn nhãn tham chiếu.', 422)
            records = body.get('items')
            if body.get('preview_id'):
                prev = c.execute('SELECT * FROM previews WHERE id=? AND expires_at>?', (body['preview_id'], time.time())).fetchone()
                if not prev:
                    raise DomainError('PREVIEW_EXPIRED', 'Bản xem trước đã hết hạn.', 410)
                preview = json.loads(prev['payload'])
                col = body.get('text_column')
                if col not in preview['columns']:
                    raise DomainError('INVALID_COLUMN', 'Chọn cột nội dung hợp lệ.', 422)
                for task in ('sentiment', 'topic'):
                    refcol = (reference or {}).get(task + '_column')
                    if refcol and refcol not in preview['columns']:
                        raise DomainError('INVALID_REFERENCE', 'Cột tham chiếu không tồn tại.', 422)
                records = [dict(text=r.get(col, ''), metadata={k:v for k,v in r.items() if k != col}, _row=n, _raw=r) for n,r in enumerate(preview['rows'], 1)]
            if not isinstance(records, list) or not 1 <= len(records) <= 500:
                raise DomainError('INVALID_ROW_COUNT', 'Cần từ 1 đến 500 phản hồi.', 422)
            clean, invalid = [], []
            for n, record in enumerate(records, 1):
                if body.get('preview_id') and any(issue['row'] == n and issue['code'] == 'COLUMN_COUNT' for issue in preview['issues']):
                    invalid.append(dict(row=n, code='COLUMN_COUNT')); continue
                try:
                    check_text(record.get('text'))
                except DomainError as exc:
                    invalid.append(dict(row=n, code=exc.code)); continue
                refs = {}
                for task in ('sentiment', 'topic'):
                    refcol = (reference or {}).get(task + '_column')
                    if refcol:
                        raw = record.get('_raw', {}).get(refcol, '')
                        mapping = reference.get(task + '_map', {})
                        value = mapping.get(raw)
                        if value is None and not mapping:
                            try: value = int(raw)
                            except (ValueError, TypeError): pass
                        if type(value) is not int or value not in [x['id'] for x in profile[task]]:
                            raise DomainError('INVALID_REFERENCE', 'Nhãn tham chiếu chưa map hợp lệ theo loại nội dung.', 422, dict(row=n, task=task, value=raw))
                        refs[task] = value
                clean.append((record, refs))
            if invalid and not body.get('skip_invalid', False):
                raise DomainError('INVALID_ROWS', 'Có phản hồi trống hoặc quá dài. Chọn bỏ dòng lỗi để tiếp tục.', 422, invalid)
            if not clean:
                raise DomainError('NO_VALID_ROWS', 'Không có phản hồi hợp lệ.', 422)
            ident, stamp = uid(), now()
            c.execute('INSERT INTO datasets VALUES(?,?,?,?,?,?,?,?)', (ident, name, profile['id'], profile['schema_id'], stamp, stamp, int(temporary), time.time()+900 if temporary else None))
            for n, (record, refs) in enumerate(clean, 1):
                revision_id = self.add_item(c, ident, record, record.get('_row', n))
                for task, value in refs.items():
                    c.execute('INSERT INTO reference_labels VALUES(?,?,?,?,?)', (revision_id, task, profile['schema_id'], value, reference['source']))
            self.remember(c, key, 'dataset', body, ident)
            result = self.dataset(ident, c)
            if invalid: result.update(skipped_count=len(invalid),issues=invalid)
            return result

    def add_item(self, c, dataset_id, record, row):
        text = check_text(record.get('text'))
        metadata = record.get('metadata') or {}
        if not isinstance(metadata, dict):
            raise DomainError('INVALID_METADATA', 'Metadata phải là một đối tượng.', 422)
        item_id, revision_id = uid(), uid()
        c.execute('INSERT INTO items VALUES(?,?,?,?)', (item_id, dataset_id, row, revision_id))
        c.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?,?)', (revision_id, item_id, 1, text, hashlib.sha256(text.encode()).hexdigest(), encode(metadata), now()))
        return revision_id

    def add_items(self, dataset_id, records):
        with self.tx() as c:
            self.require_dataset(c, dataset_id)
            count = c.execute('SELECT COUNT(*) FROM items WHERE dataset_id=?', (dataset_id,)).fetchone()[0]
            if not records or count + len(records) > 500:
                raise DomainError('INVALID_ROW_COUNT', 'Bộ phản hồi tối đa 500 dòng.', 422)
            row = c.execute('SELECT COALESCE(MAX(source_row),0) FROM items WHERE dataset_id=?', (dataset_id,)).fetchone()[0]
            for n, record in enumerate(records, row + 1):
                self.add_item(c, dataset_id, record, n)
            c.execute('UPDATE datasets SET updated_at=? WHERE id=?', (now(), dataset_id))
        return dict(added=len(records))

    def rename(self, dataset_id, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise DomainError('INVALID_NAME', 'Tên bộ phản hồi cần từ 1 đến 200 ký tự.', 422)
        with self.tx() as c:
            self.require_dataset(c, dataset_id)
            c.execute('UPDATE datasets SET name=?,updated_at=? WHERE id=?', (name.strip(), now(), dataset_id))
        return self.dataset(dataset_id)

    def delete_dataset(self, dataset_id):
        with self.tx() as c:
            self.require_dataset(c, dataset_id)
            # Cascades revoke all job leases and remove every owned snapshot atomically.
            c.execute('DELETE FROM idempotency WHERE result_id=? OR result_id IN (SELECT id FROM runs WHERE dataset_id=?)', (dataset_id, dataset_id))
            c.execute('DELETE FROM datasets WHERE id=?', (dataset_id,))

    def copy_dataset(self, dataset_id, body):
        with self.connect() as c:
            items = self.query_items(dataset_id, {}, c)
        return self.create_dataset(dict(name=body.get('name'), profile=body.get('profile'), items=[dict(text=i['text'], metadata=i['metadata']) for i in items]))

    def create_run(self, dataset_id, model, key=None, body=None):
        with self.tx() as c:
            previous = self.remember(c, key, 'run', body or dict(dataset_id=dataset_id))
            if previous:
                return self.run(previous, c)
            d = self.require_dataset(c, dataset_id)
            if not model.get('available') or model.get('schema_id') != d['schema_id']:
                raise DomainError('MODEL_UNAVAILABLE', model.get('reason') or 'Model không tương thích hoặc chưa được cài.', 409)
            rows = c.execute('SELECT id,current_revision_id FROM items WHERE dataset_id=? ORDER BY source_row', (dataset_id,)).fetchall()
            run_id, job_id, stamp = uid(), uid(), now()
            c.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,0,0,?)', (run_id, dataset_id, d['schema_id'], model['model_id'], model['model_version'], 'queued', len(rows), stamp))
            c.executemany('INSERT INTO run_items VALUES(?,?,?,NULL)', [(run_id, r['id'], r['current_revision_id']) for r in rows])
            c.execute('INSERT INTO jobs(id,run_id,status,total,created_at,updated_at,priority) VALUES(?,?,?,?,?,?,?)', (job_id, run_id, 'queued', len(rows), stamp, stamp, 1 if d['temporary'] else 0))
            c.execute('UPDATE datasets SET updated_at=?,expires_at=NULL WHERE id=?', (stamp, dataset_id))
            self.remember(c, key, 'run', body or dict(dataset_id=dataset_id), run_id)
            return self.run(run_id, c)

    def run(self, run_id, c=None):
        if c is None:
            with self.connect() as conn: return self.run(run_id, conn)
        row = c.execute('SELECT r.*,j.id job_id FROM runs r JOIN jobs j ON j.run_id=r.id WHERE r.id=?', (run_id,)).fetchone()
        if not row: raise DomainError('NOT_FOUND', 'Không tìm thấy lần phân tích.', 404)
        return dict(row)

    def runs(self, dataset_id):
        with self.connect() as c:
            self.require_dataset(c, dataset_id)
            return [self.run(r['id'], c) for r in c.execute('SELECT id FROM runs WHERE dataset_id=? ORDER BY created_at DESC', (dataset_id,))]

    def job(self, job_id, c=None):
        if c is None:
            with self.tx() as conn:
                self.recover(conn)
                return self.job(job_id, conn)
        row = c.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row: raise DomainError('NOT_FOUND', 'Không tìm thấy công việc.', 404)
        value = dict(row)
        value['cancel_requested'] = bool(value['cancel_requested'])
        errors = c.execute('SELECT item_id,revision_id,error FROM run_items WHERE run_id=? AND error IS NOT NULL', (row['run_id'],)).fetchall()
        value['errors'] = [dict(x) for x in errors]
        dataset = c.execute('SELECT d.* FROM datasets d JOIN runs r ON r.dataset_id=d.id WHERE r.id=?', (row['run_id'],)).fetchone()
        if dataset['temporary'] and row['status'] in TERMINAL:
            values = self.query_items(dataset['id'], dict(run_id=row['run_id']), c)
            value['result'] = values[0] if values else None
        return value

    def cancel(self, job_id):
        with self.tx() as c:
            j = self.job(job_id, c)
            if j['status'] not in TERMINAL:
                c.execute('UPDATE jobs SET cancel_requested=1,updated_at=? WHERE id=?', (now(), job_id))
                if j['status'] == 'queued':
                    c.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (job_id,))
                    c.execute("UPDATE runs SET status='cancelled' WHERE id=?", (j['run_id'],))
                    self.expire_quick(c, j['run_id'])
            return self.job(job_id, c)

    def retry(self, job_id, model):
        with self.tx() as c:
            self.recover(c)
            j = self.job(job_id, c)
            run = self.run(j['run_id'], c)
            if j['status'] not in TERMINAL or j['status'] == 'completed':
                raise DomainError('JOB_NOT_RETRYABLE', 'Chỉ chạy lại công việc đã dừng và còn dòng chưa hoàn tất.', 409)
            if not model.get('available') or (model.get('model_id'), model.get('model_version'), model.get('schema_id')) != (run['model_id'], run['model_version'], run['schema_id']):
                raise DomainError('MODEL_UNAVAILABLE', 'Cần đúng phiên bản model của lần chạy để tiếp tục.', 409)
            c.execute("UPDATE jobs SET status='queued',failed=0,error=NULL,cancel_requested=0,attempt_id=attempt_id+1,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?", (now(), job_id))
            c.execute("UPDATE runs SET status='queued',failed=0 WHERE id=?", (run['id'],))
            c.execute('UPDATE run_items SET error=NULL WHERE run_id=? AND NOT EXISTS(SELECT 1 FROM predictions p WHERE p.run_id=run_items.run_id AND p.item_id=run_items.item_id)', (run['id'],))
            c.execute('UPDATE datasets SET expires_at=NULL WHERE temporary=1 AND id=?', (run['dataset_id'],))
            return self.job(job_id, c)

    @staticmethod
    def review_count(item):
        return sum(bool(r and r['status'] != 'unreviewed') for r in item['reviews'].values())

    def latest_run_id(self, dataset_id, c=None):
        if c is None:
            with self.connect() as conn: return self.latest_run_id(dataset_id,conn)
        run = c.execute('SELECT id FROM runs WHERE dataset_id=? ORDER BY created_at DESC LIMIT 1',(dataset_id,)).fetchone()
        return run['id'] if run else None

    def item(self, item_id, run_id=None, c=None):
        if c is None:
            with self.connect() as conn:
                conn.execute('BEGIN')
                return self.item(item_id, run_id, conn)
        row = c.execute('SELECT i.*,d.schema_id FROM items i JOIN datasets d ON d.id=i.dataset_id WHERE i.id=?', (item_id,)).fetchone()
        if not row: raise DomainError('NOT_FOUND', 'Không tìm thấy phản hồi.', 404)
        revision_id, error = row['current_revision_id'], None
        if run_id:
            ri = c.execute('SELECT * FROM run_items WHERE run_id=? AND item_id=?', (run_id, item_id)).fetchone()
            if not ri: raise DomainError('NOT_FOUND', 'Phản hồi không thuộc lần chạy đã chọn.', 404)
            revision_id, error = ri['revision_id'], ri['error']
        rev = c.execute('SELECT * FROM revisions WHERE id=?', (revision_id,)).fetchone()
        if run_id:
            pred = c.execute('SELECT * FROM predictions WHERE item_id=? AND revision_id=? AND run_id=?', (item_id, revision_id, run_id)).fetchone()
        else:
            latest_run = self.latest_run_id(row['dataset_id'],c)
            pred = c.execute('SELECT * FROM predictions WHERE item_id=? AND revision_id=? AND run_id=?', (item_id, revision_id,latest_run)).fetchone()
            last = c.execute('SELECT error FROM run_items WHERE item_id=? AND revision_id=? AND run_id=?', (item_id,revision_id,latest_run)).fetchone()
            error = last['error'] if last else None
        prediction = dict(json.loads(pred['payload']), id=pred['id'], run_id=pred['run_id'], created_at=pred['created_at']) if pred else None
        refs = {r['task']:dict(label_id=r['label_id'], source=r['source']) for r in c.execute('SELECT * FROM reference_labels WHERE revision_id=?', (revision_id,))}
        reviews, effective = {}, {}
        for task in ('sentiment', 'topic'):
            r = c.execute('SELECT * FROM reviews WHERE revision_id=? AND task=? AND schema_id=? ORDER BY review_revision DESC LIMIT 1', (revision_id, task, row['schema_id'])).fetchone()
            reviews[task] = self.review_json(r) if r else None
            effective[task] = r['label_id'] if r and r['status'] != 'unreviewed' else (prediction[task]['label_id'] if prediction else None)
        return dict(id=item_id, dataset_id=row['dataset_id'], revision_id=revision_id, revision=rev['revision'], source_row=row['source_row'], text=rev['text'], metadata=json.loads(rev['metadata_json']), reference=refs, prediction=prediction, reviews=reviews, effective=effective, stale=revision_id != row['current_revision_id'], error=error)

    def query_items(self, dataset_id, filters, c=None):
        if c is None:
            with self.connect() as conn:
                conn.execute('BEGIN')
                return self.query_items(dataset_id, filters, conn)
        dataset = self.require_dataset(c, dataset_id)
        for task in ('sentiment','topic'):
            if filters.get(task) is not None and int(filters[task]) not in [x['id'] for x in profile_for(dataset['profile'])[task]]:
                raise DomainError('INVALID_FILTER','Nhãn lọc không thuộc loại nội dung này.',422)
        run_id = filters.get('run_id')
        if run_id and self.run(run_id, c)['dataset_id'] != dataset_id:
            raise DomainError('RUN_DATASET_MISMATCH', 'Lần chạy không thuộc bộ phản hồi.', 422)
        if run_id:
            ids = c.execute('SELECT i.id FROM items i JOIN run_items ri ON ri.item_id=i.id WHERE i.dataset_id=? AND ri.run_id=?', (dataset_id, run_id))
        else:
            ids = c.execute('SELECT id FROM items WHERE dataset_id=?', (dataset_id,))
        items = [self.item(r['id'], run_id, c) for r in ids]
        source = filters.get('label_source', 'effective')
        review_status = filters.get('review_status', 'all')
        if source not in ('effective', 'ai') or review_status not in ('all', 'unreviewed', 'partial', 'reviewed', 'needs_review'):
            raise DomainError('INVALID_FILTER', 'Bộ lọc không hợp lệ.', 422)
        def labels(i):
            return i['effective'] if source == 'effective' else {t:i['prediction'][t]['label_id'] if i['prediction'] else None for t in ('sentiment', 'topic')}
        def keep(i):
            if filters.get('q') and str(filters['q']).casefold() not in i['text'].casefold(): return False
            for task in ('sentiment', 'topic'):
                if filters.get(task) is not None and labels(i)[task] != int(filters[task]): return False
            n = self.review_count(i)
            if review_status in ('unreviewed', 'partial', 'reviewed') and n != {'unreviewed':0, 'partial':1, 'reviewed':2}[review_status]: return False
            p = i['prediction']
            needs = n < 2 or bool(i['error']) or bool(p and (p.get('truncated') or any(max(p[t]['scores']) < .6 for t in ('sentiment', 'topic'))))
            return review_status != 'needs_review' or needs
        items = [i for i in items if keep(i)]
        sort, direction = filters.get('sort', 'source_row'), filters.get('direction', 'asc')
        if sort not in ('source_row', 'text', 'sentiment', 'topic') or direction not in ('asc', 'desc'):
            raise DomainError('INVALID_FILTER', 'Thứ tự sắp xếp không hợp lệ.', 422)
        items.sort(key=lambda i: (labels(i)[sort] is None, labels(i)[sort] if labels(i)[sort] is not None else -1, i['source_row']) if sort in ('sentiment', 'topic') else (i[sort], i['source_row']), reverse=direction == 'desc')
        return items

    def summary(self, dataset_id, filters):
        items = self.query_items(dataset_id, filters)
        sentiment, topic, cross = {}, {}, {}
        for i in items:
            labels = i['effective'] if filters.get('label_source', 'effective') == 'effective' else {t:i['prediction'][t]['label_id'] if i['prediction'] else None for t in ('sentiment', 'topic')}
            s, t = labels['sentiment'], labels['topic']
            if s is not None: sentiment[s] = sentiment.get(s, 0) + 1
            if t is not None: topic[t] = topic.get(t, 0) + 1
            if s is not None and t is not None: cross[(s,t)] = cross.get((s,t), 0) + 1
        return dict(total=len(items), processed=sum(bool(i['prediction']) for i in items), reviewed=sum(self.review_count(i) == 2 for i in items), partial_review=sum(self.review_count(i) == 1 for i in items), unreviewed=sum(self.review_count(i) == 0 for i in items), truncated=sum(bool(i['prediction'] and i['prediction'].get('truncated')) for i in items), errors=sum(bool(i['error']) for i in items), sentiment=[dict(label_id=k,count=v) for k,v in sorted(sentiment.items())], topic=[dict(label_id=k,count=v) for k,v in sorted(topic.items())], cross=[dict(sentiment=k[0],topic=k[1],count=v) for k,v in sorted(cross.items())], denominator=dict(sentiment=sum(sentiment.values()),topic=sum(topic.values()),cross=sum(cross.values())), run_id=filters.get('run_id'), label_source=filters.get('label_source','effective'))

    def edit_text(self, item_id, text, expected_revision):
        check_text(text)
        with self.tx() as c:
            item = self.item(item_id, c=c)
            if item['revision'] != expected_revision: raise DomainError('REVISION_CONFLICT', 'Nội dung đã được sửa. Tải lại trước khi lưu.', 409)
            revision_id = uid()
            c.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?,?)', (revision_id, item_id, expected_revision + 1, text, hashlib.sha256(text.encode()).hexdigest(), encode(item['metadata']), now()))
            c.execute('UPDATE items SET current_revision_id=? WHERE id=?', (revision_id, item_id))
            c.execute('UPDATE datasets SET updated_at=? WHERE id=?', (now(), item['dataset_id']))
            return self.item(item_id, c=c)

    @staticmethod
    def review_json(r):
        return dict(revision=r['review_revision'],status=r['status'],label_id=r['label_id'],note=r['note'],source_prediction_id=r['source_prediction_id'],created_at=r['created_at'])

    def review(self, item_id, body, restore=False):
        task = body.get('task')
        if task not in ('sentiment', 'topic'): raise DomainError('INVALID_TASK', 'Tác vụ không hợp lệ.', 422)
        with self.tx() as c:
            i = self.item(item_id, body.get('run_id'), c=c)
            current_input = self.item(item_id, c=c)
            if i['revision_id'] != current_input['revision_id']:
                raise DomainError('REVISION_CONFLICT', 'Lần chạy đã chọn dùng nội dung cũ. Chọn nội dung hiện tại để duyệt.', 409)
            if i['revision'] != body.get('expected_revision'): raise DomainError('REVISION_CONFLICT', 'Nội dung đã thay đổi.', 409)
            current = i['reviews'][task]
            revision = current['revision'] if current else 0
            if revision != body.get('expected_review_revision'): raise DomainError('REVIEW_CONFLICT', 'Bản duyệt đã thay đổi. Tải lại trước khi lưu.', 409)
            source_prediction_id = i['prediction']['id'] if i['prediction'] else None
            if restore:
                if body.get('revision_id') and body['revision_id'] != i['revision_id']:
                    raise DomainError('INVALID_RESTORE', 'Bản duyệt lịch sử thuộc phiên bản nội dung khác.', 422)
                historic = c.execute('SELECT * FROM reviews WHERE revision_id=? AND task=? AND review_revision=?', (i['revision_id'], task, body.get('review_revision'))).fetchone()
                if not historic: raise DomainError('INVALID_RESTORE', 'Bản duyệt lịch sử không khớp nội dung/schema.', 422)
                status, label, note, source_prediction_id = historic['status'], historic['label_id'], historic['note'], historic['source_prediction_id']
            else:
                status, label, note = body.get('status'), body.get('label_id'), body.get('note', '')
            dataset = self.require_dataset(c, i['dataset_id'])
            if status not in ('unreviewed', 'confirmed', 'corrected') or not isinstance(note, str) or len(note) > 10000:
                raise DomainError('INVALID_REVIEW', 'Trạng thái hoặc ghi chú không hợp lệ.', 422)
            if status == 'unreviewed': label = None
            elif type(label) is not int or label not in [x['id'] for x in profile_for(dataset['profile'])[task]]:
                raise DomainError('INVALID_LABEL', 'Nhãn không thuộc loại nội dung này.', 422)
            if not restore:
                prediction = i['prediction']
                explicit_source = body.get('source_prediction_id')
                if explicit_source is not None:
                    source = c.execute('SELECT p.* FROM predictions p JOIN runs r ON r.id=p.run_id WHERE p.id=? AND p.item_id=? AND p.revision_id=? AND r.schema_id=?',
                                       (explicit_source, item_id, i['revision_id'], dataset['schema_id'])).fetchone()
                    prediction = json.loads(source['payload']) if source else None
                    source_prediction_id = source['id'] if source else None
                    if not prediction or prediction.get('schema_id') != dataset['schema_id']:
                        raise DomainError('CONFIRM_REQUIRES_PREDICTION', 'Dự đoán nguồn không khớp nội dung/schema hiện tại.', 409)
                elif status != 'confirmed' and 'source_prediction_id' in body:
                    # Explicit null clears provenance after a deliberate manual edit.
                    source_prediction_id = None
                if status == 'confirmed' and (not prediction or prediction.get('schema_id') != dataset['schema_id'] or prediction.get(task,{}).get('label_id') != label):
                    raise DomainError('CONFIRM_REQUIRES_PREDICTION', 'Chỉ xác nhận nhãn khớp dự đoán AI hiện tại.', 409)
            stamp = now()
            c.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?,?,?)', (uid(), item_id, i['revision_id'], dataset['schema_id'], task, revision+1, status, label, note, source_prediction_id, stamp))
            c.execute('UPDATE datasets SET updated_at=? WHERE id=?', (stamp, i['dataset_id']))
            return dict(revision=revision+1,status=status,label_id=label,note=note,source_prediction_id=source_prediction_id,created_at=stamp)

    def history(self, item_id, kind):
        with self.connect() as c:
            c.execute('BEGIN')
            self.item(item_id, c=c)
            if kind == 'revisions':
                return [dict(revision_id=r['id'],revision=r['revision'],text=r['text'],metadata=json.loads(r['metadata_json']),created_at=r['created_at']) for r in c.execute('SELECT * FROM revisions WHERE item_id=? ORDER BY revision', (item_id,))]
            return [dict(self.review_json(r),task=r['task'],revision_id=r['revision_id'],schema_id=r['schema_id'],input_revision=c.execute('SELECT revision FROM revisions WHERE id=?',(r['revision_id'],)).fetchone()[0]) for r in c.execute('SELECT * FROM reviews WHERE item_id=? ORDER BY created_at,review_revision', (item_id,))]

    def export(self, dataset_id, filters):
        with self.tx() as c:
            items = self.query_items(dataset_id, filters, c)
            dataset = self.dataset(dataset_id, c)
            selected_run_id = filters.get('run_id') or self.latest_run_id(dataset_id,c)
            columns = ['item_id','source_row','text','metadata','revision_id','revision','schema_id','selected_run_id','prediction_status','prediction_id','run_id','model_id','model_version','label_source','selected_sentiment','selected_topic','ai_sentiment','ai_topic','sentiment_scores','topic_scores','reference_sentiment','reference_sentiment_source','reference_topic','reference_topic_source','review_sentiment','review_sentiment_status','review_sentiment_revision','review_sentiment_note','review_sentiment_source_prediction_id','review_topic','review_topic_status','review_topic_revision','review_topic_note','review_topic_source_prediction_id','effective_sentiment','effective_topic','token_count_before_truncation','truncated','warnings','error']
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader()
            for i in items:
                p = i['prediction'] or {}
                row = dict(item_id=i['id'],source_row=i['source_row'],text=i['text'],metadata=encode(i['metadata']),revision_id=i['revision_id'],revision=i['revision'],schema_id=dataset['schema_id'],selected_run_id=selected_run_id or '',prediction_status='processed' if p else ('failed' if i['error'] else 'unprocessed'),prediction_id=p.get('id',''),run_id=p.get('run_id',''),model_id=p.get('model_id',''),model_version=p.get('model_version',''),ai_sentiment=p.get('sentiment',{}).get('label_id',''),ai_topic=p.get('topic',{}).get('label_id',''),sentiment_scores=encode(p.get('sentiment',{}).get('scores',[])),topic_scores=encode(p.get('topic',{}).get('scores',[])),effective_sentiment=i['effective']['sentiment'],effective_topic=i['effective']['topic'],token_count_before_truncation=p.get('token_count_before_truncation',''),truncated=p.get('truncated',False),warnings=encode(p.get('warnings',[])),error=i['error'])
                row['label_source'] = filters.get('label_source','effective')
                for task in ('sentiment','topic'):
                    row['selected_'+task] = row['ai_'+task] if row['label_source'] == 'ai' else i['effective'][task]
                for task in ('sentiment','topic'):
                    ref, review = i['reference'].get(task,{ }), i['reviews'].get(task) or {}
                    row.update({f'reference_{task}':ref.get('label_id',''),f'reference_{task}_source':ref.get('source',''),f'review_{task}':review.get('label_id',''),f'review_{task}_status':review.get('status','unreviewed'),f'review_{task}_revision':review.get('revision',0),f'review_{task}_note':review.get('note',''),f'review_{task}_source_prediction_id':review.get('source_prediction_id','')})
                # Escape user-controlled strings even after leading whitespace/control chars.
                for k,v in row.items():
                    if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')): row[k] = "'" + v
                writer.writerow(row)
            ident, stamp = uid(), now()
            c.execute('INSERT INTO exports VALUES(?,?,?,?,?,?,?,?)', (ident,dataset_id,selected_run_id,encode(filters),encode(items),stream.getvalue().encode('utf-8-sig'),len(items),stamp))
            return dict(id=ident,row_count=len(items),created_at=stamp,url=f'/api/v1/exports/{ident}')

    def export_bytes(self, ident):
        with self.connect() as c:
            row = c.execute('SELECT csv_blob FROM exports WHERE id=?',(ident,)).fetchone()
            if not row: raise DomainError('NOT_FOUND','Không tìm thấy bản xuất.',404)
            return bytes(row[0])

    def worker_health(self):
        with self.connect() as c:
            row = c.execute('SELECT * FROM worker_status WHERE id=1').fetchone()
            return dict(alive=bool(row and row['expires_at'] > time.time()), **({k:row[k] for k in ('owner','pid','heartbeat_at')} if row else {}))
