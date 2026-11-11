import csv
import hashlib
import io
import json
import math
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from services.analytics import aggregate_attention, selected_labels
from services.review_signals import evaluate_item_signals, resolve_policy_metadata

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


def _task_scores_need_review(prediction, task):
    task_pred = prediction.get(task) if isinstance(prediction, dict) else None
    scores = task_pred.get('scores') if isinstance(task_pred, dict) else None
    if not isinstance(scores, list) or not scores:
        return True
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in scores):
        return True
    return max(scores) < .6


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

MIGRATION_2 = '''
CREATE TABLE sensitivity_experiments (
  job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
  temporary_dataset_id TEXT NOT NULL UNIQUE REFERENCES datasets(id) ON DELETE CASCADE,
  source_dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  source_item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  source_revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
  baseline_item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  variant_item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  context_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX sensitivity_source_item ON sensitivity_experiments(source_item_id);
CREATE INDEX sensitivity_source_dataset ON sensitivity_experiments(source_dataset_id);
CREATE INDEX sensitivity_created ON sensitivity_experiments(created_at);
CREATE TABLE sensitivity_rate_limits (
  id TEXT PRIMARY KEY,
  created_ts REAL NOT NULL
);
CREATE INDEX sensitivity_rate_created ON sensitivity_rate_limits(created_ts);
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
            for version, sql in ((1, MIGRATION_1), (2, MIGRATION_2)):
                conn.execute('BEGIN IMMEDIATE')
                try:
                    conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
                    if not conn.execute('SELECT 1 FROM schema_migrations WHERE version=?', (version,)).fetchone():
                        for statement in sql.split(';'):
                            if statement.strip(): conn.execute(statement)
                        conn.execute('INSERT INTO schema_migrations VALUES(?,?)', (version, now()))
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
        self.cleanup()

    def database_version(self):
        with self.connect() as c:
            row = c.execute('SELECT COALESCE(MAX(version), 0) FROM schema_migrations').fetchone()
            return int(row[0]) if row else 0

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

    def cleanup_expired_in_tx(self, c):
        self.recover(c)
        now_ts = time.time()
        # Delete dependent experiments BEFORE their quick source. A source FK cascade
        # only removes the mapping, otherwise leaving its internal job runnable as quick.
        expired_sources = c.execute('''SELECT d.id FROM datasets d WHERE d.temporary=1
            AND d.expires_at IS NOT NULL AND d.expires_at<=?
            AND NOT EXISTS (SELECT 1 FROM runs r JOIN jobs j ON j.run_id=r.id
                WHERE r.dataset_id=d.id AND j.status NOT IN
                ('completed','completed_with_errors','failed','cancelled','interrupted'))''', (now_ts,)).fetchall()
        for source in expired_sources:
            self._delete_linked_experiment_datasets(c, source['id'])
        # A stale expiry marker must never revoke queued or live inference.
        c.execute("""DELETE FROM datasets WHERE temporary=1 AND expires_at IS NOT NULL AND expires_at<=?
                     AND NOT EXISTS (SELECT 1 FROM runs r JOIN jobs j ON j.run_id=r.id
                         WHERE r.dataset_id=datasets.id AND j.status NOT IN
                         ('completed','completed_with_errors','failed','cancelled','interrupted'))""", (now_ts,))
        c.execute("DELETE FROM idempotency WHERE operation='sensitivity' AND result_id NOT IN (SELECT job_id FROM sensitivity_experiments)")
        c.execute('DELETE FROM sensitivity_rate_limits WHERE created_ts<=?', (now_ts - 60.0,))

    def cleanup(self):
        with self.tx() as c:
            c.execute('DELETE FROM previews WHERE expires_at<?', (time.time(),))
            self.cleanup_expired_in_tx(c)

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
        latest = c.execute('SELECT id FROM runs WHERE dataset_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1', (dataset_id,)).fetchone()
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

    def _require_not_sensitivity_dataset(self, c, dataset_id):
        if c.execute('SELECT 1 FROM sensitivity_experiments WHERE temporary_dataset_id=? LIMIT 1', (dataset_id,)).fetchone():
            raise DomainError('EXPERIMENT_READ_ONLY', 'Không thể chỉnh sửa dữ liệu tạm của thử nghiệm độ nhạy.', 409)

    def _require_not_sensitivity_item(self, c, item_id):
        if c.execute(
            'SELECT 1 FROM sensitivity_experiments se JOIN items i ON i.dataset_id=se.temporary_dataset_id WHERE i.id=? LIMIT 1',
            (item_id,),
        ).fetchone():
            raise DomainError('EXPERIMENT_READ_ONLY', 'Không thể chỉnh sửa phản hồi tạm của thử nghiệm độ nhạy.', 409)

    @staticmethod
    def _resolve_execution_identity(execution_resolver, profile):
        if execution_resolver is None:
            raise DomainError('MODEL_UNAVAILABLE', 'Model chưa sẵn sàng.', 409)
        try:
            return execution_resolver(profile)
        except DomainError:
            raise
        except Exception as exc:
            if type(exc).__name__ == 'ModelUnavailable':
                raise DomainError('MODEL_UNAVAILABLE', str(exc) or 'Model chưa sẵn sàng.', 409) from None
            raise

    def create_dataset(self, body, key=None, temporary=False):
        profile = profile_for(body.get('profile'))
        name = body.get('name', '').strip()
        if not name or len(name) > 200:
            raise DomainError('INVALID_NAME', 'Tên bộ phản hồi cần từ 1 đến 200 ký tự.', 422)
        with self.tx() as c:
            return self._create_dataset_tx(c, body, key=key, temporary=temporary, profile=profile, name=name)

    def _create_dataset_tx(self, c, body, key=None, temporary=False, profile=None, name=None):
        profile = profile or profile_for(body.get('profile'))
        name = name if name is not None else body.get('name', '').strip()
        if not name or len(name) > 200:
            raise DomainError('INVALID_NAME', 'Tên bộ phản hồi cần từ 1 đến 200 ký tự.', 422)
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
            self._require_not_sensitivity_dataset(c, dataset_id)
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
            self._require_not_sensitivity_dataset(c, dataset_id)
            c.execute('UPDATE datasets SET name=?,updated_at=? WHERE id=?', (name.strip(), now(), dataset_id))
        return self.dataset(dataset_id)

    def _delete_linked_experiment_datasets(self, c, dataset_id):
        rows = c.execute(
            'SELECT temporary_dataset_id, job_id FROM sensitivity_experiments WHERE source_dataset_id=?',
            (dataset_id,),
        ).fetchall()
        for exp in rows:
            temp_id = exp['temporary_dataset_id']
            c.execute(
                'DELETE FROM idempotency WHERE result_id=? OR result_id=? OR result_id IN (SELECT id FROM runs WHERE dataset_id=?)',
                (exp['job_id'], temp_id, temp_id),
            )
            # Cascades fence queued/running workers by deleting their job lease.
            c.execute('DELETE FROM datasets WHERE id=?', (temp_id,))

    def validate_quick_source(self, c, job_id, source_prediction_id=None):
        """Validate a server-created, current quick snapshot in this short transaction.

        Callers must repeat this check after asynchronous work, without holding c
        across inference/network awaits. Deleted sources are 404; known expiry 410.
        """
        job = c.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not job:
            raise DomainError('NOT_FOUND', 'Không tìm thấy công việc.', 404)
        run = c.execute('SELECT * FROM runs WHERE id=?', (job['run_id'],)).fetchone()
        dataset = self.require_dataset(c, run['dataset_id'])
        unsupported = (not dataset['temporary'] or c.execute(
            'SELECT 1 FROM sensitivity_experiments WHERE temporary_dataset_id=?', (dataset['id'],)
        ).fetchone())
        rows = c.execute('SELECT id FROM items WHERE dataset_id=?', (dataset['id'],)).fetchall()
        run_count = c.execute('SELECT COUNT(*) FROM runs WHERE dataset_id=?', (dataset['id'],)).fetchone()[0]
        if unsupported or len(rows) != 1 or run_count != 1:
            raise DomainError('INVALID_EXPERIMENT_SOURCE', 'Nguồn tạm không phải kết quả phân tích một câu được hỗ trợ.', 422)
        item = self.item(rows[0]['id'], run['id'], c)
        if item['metadata'].get('_temporary_source') != 'quick-analysis-v1':
            raise DomainError('INVALID_EXPERIMENT_SOURCE', 'Nguồn tạm không phải kết quả phân tích một câu được hỗ trợ.', 422)
        if job['status'] != 'completed' or run['status'] != 'completed' or job['completed'] != 1 or job['failed'] != 0:
            raise DomainError('JOB_NOT_READY', 'Công việc phân tích chưa hoàn thành.', 409)
        expiry = dataset['expires_at']
        if type(expiry) not in (int, float) or not math.isfinite(expiry):
            raise DomainError('SOURCE_CONFLICT', 'Thời hạn kết quả nguồn không hợp lệ.', 409)
        if expiry <= time.time():
            raise DomainError('JOB_EXPIRED', 'Kết quả phân tích đã hết hạn. Phân tích lại câu để tiếp tục.', 410)
        revision = c.execute('SELECT * FROM revisions WHERE id=?', (item['revision_id'],)).fetchone()
        digest = hashlib.sha256(item['text'].encode('utf-8')).hexdigest()
        if item['stale'] or revision['text_hash'] != digest:
            raise DomainError('REVISION_CONFLICT', 'Nội dung phản hồi nguồn đã thay đổi.', 409)
        prediction = item['prediction']
        if not prediction or (source_prediction_id is not None and prediction['id'] != source_prediction_id):
            raise DomainError('SOURCE_CONFLICT', 'Dự đoán nguồn không khớp với kết quả hiện tại. Tải lại để tiếp tục.', 409)
        from services.sensitivity import _valid_pair_prediction
        profile = profile_for(dataset['profile'])
        identity = {k: run[k] for k in ('schema_id', 'model_id', 'model_version')}
        valid = (dataset['schema_id'] == profile['schema_id'] == run['schema_id']
                 and prediction.get('item_id') == item['id']
                 and prediction.get('revision_id') == item['revision_id']
                 and prediction.get('run_id') == run['id']
                 and isinstance(prediction.get('warnings'), list)
                 and type(prediction.get('token_count_before_truncation')) is int
                 and prediction['token_count_before_truncation'] >= 0
                 and _valid_pair_prediction(prediction, identity, profile, expected_item=item))
        if valid:
            valid = all(prediction[task]['label_id'] == profile[task][max(
                range(len(prediction[task]['scores'])), key=prediction[task]['scores'].__getitem__
            )]['id'] for task in ('sentiment', 'topic'))
        if not valid:
            raise DomainError('INVALID_PREDICTION', 'Kết quả phân tích nguồn không đủ dữ liệu hợp lệ.', 409)
        return {'job': dict(job), 'run': dict(run), 'dataset': dict(dataset), 'item': item,
                'source_expires_at': float(expiry), 'text_sha256': digest}

    def delete_dataset(self, dataset_id):
        with self.tx() as c:
            self.require_dataset(c, dataset_id)
            self._require_not_sensitivity_dataset(c, dataset_id)
            self._delete_linked_experiment_datasets(c, dataset_id)
            # Cascades revoke all job leases and remove every owned snapshot atomically.
            c.execute('DELETE FROM idempotency WHERE result_id=? OR result_id IN (SELECT id FROM runs WHERE dataset_id=?)', (dataset_id, dataset_id))
            c.execute('DELETE FROM datasets WHERE id=?', (dataset_id,))

    def copy_dataset(self, dataset_id, body):
        with self.connect() as c:
            c.execute('BEGIN')
            self.require_dataset(c, dataset_id)
            self._require_not_sensitivity_dataset(c, dataset_id)
            items = self.query_items(dataset_id, {}, c)
        return self.create_dataset(dict(name=body.get('name'), profile=body.get('profile'), items=[dict(text=i['text'], metadata=i['metadata']) for i in items]))

    def create_run(self, dataset_id, model, key=None, body=None):
        with self.tx() as c:
            return self._create_run_tx(c, dataset_id, model, key=key, body=body, allow_sensitivity=False)

    def _create_run_tx(self, c, dataset_id, model, key=None, body=None, allow_sensitivity=False):
        previous = self.remember(c, key, 'run', body or dict(dataset_id=dataset_id))
        if previous:
            return self.run(previous, c)
        d = self.require_dataset(c, dataset_id)
        if not allow_sensitivity:
            self._require_not_sensitivity_dataset(c, d['id'])
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
            return [self.run(r['id'], c) for r in c.execute('SELECT id FROM runs WHERE dataset_id=? ORDER BY created_at DESC, rowid DESC', (dataset_id,))]

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
        is_sensitivity = bool(c.execute('SELECT 1 FROM sensitivity_experiments WHERE job_id=?', (job_id,)).fetchone())
        value['kind'] = 'sensitivity' if is_sensitivity else ('quick' if dataset['temporary'] else 'analysis')
        if is_sensitivity:
            value['result'] = None
        elif dataset['temporary'] and row['status'] in TERMINAL:
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

    def retry(self, job_id, model=None, execution_resolver=None):
        with self.tx() as c:
            self.cleanup_expired_in_tx(c)
            j = self.job(job_id, c)
            run = self.run(j['run_id'], c)
            if j['status'] not in TERMINAL or j['status'] == 'completed':
                raise DomainError('JOB_NOT_RETRYABLE', 'Chỉ chạy lại công việc đã dừng và còn dòng chưa hoàn tất.', 409)
            exp = c.execute('SELECT * FROM sensitivity_experiments WHERE job_id=?', (job_id,)).fetchone()
            if exp:
                context = json.loads(exp['context_json'])
                if context.get('source_kind') == 'quick':
                    self.validate_quick_source(c, context['source_job_id'], context['source']['prediction_id'])
                pred_count = c.execute('SELECT COUNT(*) FROM predictions WHERE run_id=?', (run['id'],)).fetchone()[0]
                if pred_count >= 2:
                    raise DomainError('JOB_NOT_RETRYABLE', 'Thử nghiệm đã có đủ hai kết quả.', 409)
                src_item = c.execute('SELECT current_revision_id FROM items WHERE id=?', (exp['source_item_id'],)).fetchone()
                if not src_item:
                    raise DomainError('NOT_FOUND', 'Không tìm thấy phản hồi nguồn.', 404)
                cur_rev = c.execute('SELECT text_hash FROM revisions WHERE id=?', (src_item['current_revision_id'],)).fetchone()
                if (
                    src_item['current_revision_id'] != context['source']['revision_id']
                    or not cur_rev
                    or cur_rev['text_hash'] != context['source']['text_sha256']
                ):
                    raise DomainError('REVISION_CONFLICT', 'Nội dung phản hồi nguồn đã thay đổi. Tạo thử nghiệm mới để chạy trên nội dung hiện tại.', 409)
                current_identity = self._resolve_execution_identity(execution_resolver, context['execution']['profile'])
                if current_identity != context['execution']:
                    raise DomainError('MODEL_IDENTITY_CHANGED', 'Model hoặc cấu hình tiền xử lý đã thay đổi so với lần thử nghiệm trước.', 409)
                existing_active = c.execute(
                    """SELECT se.job_id FROM sensitivity_experiments se
                       JOIN jobs j ON j.id=se.job_id
                       WHERE se.source_item_id=? AND se.job_id!=?
                         AND j.status NOT IN ('completed','completed_with_errors','failed','cancelled','interrupted')
                       LIMIT 1""",
                    (exp['source_item_id'], job_id),
                ).fetchone()
                if existing_active:
                    raise DomainError(
                        'EXPERIMENT_IN_PROGRESS',
                        'Phản hồi này đang có một thử nghiệm độ nhạy chưa kết thúc.',
                        409,
                        {'existing_job_id': existing_active['job_id']},
                    )
                active_count = c.execute(
                    """SELECT COUNT(*) FROM sensitivity_experiments se
                       JOIN jobs j ON j.id=se.job_id
                       WHERE j.status NOT IN ('completed','completed_with_errors','failed','cancelled','interrupted')"""
                ).fetchone()[0]
                if active_count >= 4:
                    raise DomainError(
                        'EXPERIMENT_LIMIT',
                        'Đã đạt giới hạn 4 thử nghiệm độ nhạy đang chạy đồng thời.',
                        429,
                        {'limit': 4, 'reason': 'CONCURRENT_LIMIT'},
                    )
                context['attempt'] = {'error_code': None, 'model_input_equal': None}
                c.execute('UPDATE sensitivity_experiments SET context_json=? WHERE job_id=?', (encode(context), job_id))
                c.execute('DELETE FROM predictions WHERE run_id=?', (run['id'],))
                c.execute("UPDATE jobs SET status='queued',completed=0,failed=0,error=NULL,cancel_requested=0,attempt_id=attempt_id+1,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?", (now(), job_id))
                c.execute("UPDATE runs SET status='queued',completed=0,failed=0 WHERE id=?", (run['id'],))
                c.execute('UPDATE run_items SET error=NULL WHERE run_id=?', (run['id'],))
                c.execute('UPDATE datasets SET expires_at=NULL WHERE temporary=1 AND id=?', (run['dataset_id'],))
                return self.job(job_id, c)
            if not model or not model.get('available') or (model.get('model_id'), model.get('model_version'), model.get('schema_id')) != (run['model_id'], run['model_version'], run['schema_id']):
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
        run = c.execute('SELECT id FROM runs WHERE dataset_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1',(dataset_id,)).fetchone()
        return run['id'] if run else None

    def item(self, item_id, run_id=None, c=None):
        if c is None:
            with self.connect() as conn:
                conn.execute('BEGIN')
                return self.item(item_id, run_id, conn)
        row = c.execute('SELECT i.*,d.schema_id,d.profile FROM items i JOIN datasets d ON d.id=i.dataset_id WHERE i.id=?', (item_id,)).fetchone()
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
        raw_payload = json.loads(pred['payload'], parse_constant=lambda _: None) if pred else None
        prediction = dict(raw_payload if isinstance(raw_payload, dict) else {}, id=pred['id'], run_id=pred['run_id'], created_at=pred['created_at']) if pred else None
        refs = {r['task']:dict(label_id=r['label_id'], source=r['source']) for r in c.execute('SELECT * FROM reference_labels WHERE revision_id=?', (revision_id,))}
        reviews, effective = {}, {}
        for task in ('sentiment', 'topic'):
            r = c.execute('SELECT * FROM reviews WHERE revision_id=? AND task=? AND schema_id=? ORDER BY review_revision DESC LIMIT 1', (revision_id, task, row['schema_id'])).fetchone()
            reviews[task] = self.review_json(r) if r else None
            if r and r['status'] != 'unreviewed':
                effective[task] = r['label_id']
            else:
                task_pred = prediction.get(task) if isinstance(prediction, dict) else None
                effective[task] = task_pred['label_id'] if isinstance(task_pred, dict) and type(task_pred.get('label_id')) is int else None
        review_signals = evaluate_item_signals(prediction, reviews, profile_for(row['profile']))
        return dict(id=item_id, dataset_id=row['dataset_id'], revision_id=revision_id, revision=rev['revision'], source_row=row['source_row'], text=rev['text'], metadata=json.loads(rev['metadata_json']), reference=refs, prediction=prediction, reviews=reviews, effective=effective, review_signals=review_signals, stale=revision_id != row['current_revision_id'], error=error)

    def run_snapshot(self, dataset_id, filters=None, c=None):
        if c is None:
            with self.connect() as conn:
                conn.execute('BEGIN')
                return self.run_snapshot(dataset_id, filters, conn)
        self.require_dataset(c, dataset_id)
        run_id = (filters or {}).get('run_id') or None
        if run_id:
            run = self.run(run_id, c)
            if run['dataset_id'] != dataset_id:
                raise DomainError('RUN_DATASET_MISMATCH', 'Lần chạy không thuộc bộ phản hồi.', 422)
            return dict(revision_scope='run', resolved_run_id=run['id'], run_status=run['status'])
        latest = c.execute('SELECT id,status FROM runs WHERE dataset_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1', (dataset_id,)).fetchone()
        return dict(revision_scope='current', resolved_run_id=latest['id'] if latest else None, run_status=latest['status'] if latest else None)

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
        review_signal = filters.get('review_signal', 'all')
        if (
            source not in ('effective', 'ai')
            or review_status not in ('all', 'unreviewed', 'partial', 'reviewed', 'needs_review')
            or review_signal not in ('all', 'model_uncertain', 'sentiment_uncertain', 'topic_uncertain', 'truncated', 'pending_signal_review')
        ):
            raise DomainError('INVALID_FILTER', 'Bộ lọc không hợp lệ.', 422)
        def labels(i):
            return selected_labels(i, source)
        def matches_signal(i):
            if review_signal == 'all':
                return True
            sig = i['review_signals']
            if review_signal == 'model_uncertain':
                return sig['sentiment']['state'] == 'flagged' or sig['topic']['state'] == 'flagged'
            if review_signal == 'sentiment_uncertain':
                return sig['sentiment']['state'] == 'flagged'
            if review_signal == 'topic_uncertain':
                return sig['topic']['state'] == 'flagged'
            if review_signal == 'truncated':
                return sig['truncated'] is True
            return sig['pending_signal_review'] is True
        def keep(i):
            if filters.get('q') and str(filters['q']).casefold() not in i['text'].casefold(): return False
            for task in ('sentiment', 'topic'):
                if filters.get(task) is not None and labels(i)[task] != int(filters[task]): return False
            n = self.review_count(i)
            if review_status in ('unreviewed', 'partial', 'reviewed') and n != {'unreviewed':0, 'partial':1, 'reviewed':2}[review_status]: return False
            p = i['prediction']
            needs = n < 2 or bool(i['error']) or bool(isinstance(p, dict) and p and (p.get('truncated') or any(_task_scores_need_review(p, t) for t in ('sentiment', 'topic'))))
            if review_status == 'needs_review' and not needs: return False
            return matches_signal(i)
        items = [i for i in items if keep(i)]
        sort, direction = filters.get('sort', 'source_row'), filters.get('direction', 'asc')
        if sort not in ('source_row', 'text', 'sentiment', 'topic') or direction not in ('asc', 'desc'):
            raise DomainError('INVALID_FILTER', 'Thứ tự sắp xếp không hợp lệ.', 422)
        items.sort(key=lambda i: (labels(i)[sort] is None, labels(i)[sort] if labels(i)[sort] is not None else -1, i['source_row'], i['id']) if sort in ('sentiment', 'topic') else (i[sort], i['source_row'], i['id']), reverse=direction == 'desc')
        return items

    def items_page(self, dataset_id, filters, page=1, page_size=25, c=None):
        if page < 1 or page_size < 1 or page_size > 500:
            raise DomainError('INVALID_PAGINATION', 'Trang không hợp lệ.', 422)
        filters = filters or {}
        if c is None:
            with self.connect() as conn:
                conn.execute('BEGIN')
                return self.items_page(dataset_id, filters, page, page_size, conn)
        items = self.query_items(dataset_id, filters, c)
        snapshot = self.run_snapshot(dataset_id, filters, c)
        start = (page - 1) * page_size
        return dict(
            items=items[start:start + page_size],
            total=len(items),
            page=page,
            page_size=page_size,
            run_id=filters.get('run_id') or None,
            **snapshot,
        )

    def summary(self, dataset_id, filters, c=None):
        filters = filters or {}
        if c is None:
            with self.connect() as conn:
                conn.execute('BEGIN')
                return self.summary(dataset_id, filters, conn)
        dataset = self.require_dataset(c, dataset_id)
        profile = profile_for(dataset['profile'])
        items = self.query_items(dataset_id, filters, c)
        snapshot = self.run_snapshot(dataset_id, filters, c)
        source = filters.get('label_source', 'effective')
        sentiment, topic, cross = {}, {}, {}
        for i in items:
            labels = selected_labels(i, source)
            s, t = labels['sentiment'], labels['topic']
            if s is not None: sentiment[s] = sentiment.get(s, 0) + 1
            if t is not None: topic[t] = topic.get(t, 0) + 1
            if s is not None and t is not None: cross[(s,t)] = cross.get((s,t), 0) + 1
        attention = aggregate_attention(items, profile, source)
        review_policy = resolve_policy_metadata(profile['schema_id'])
        return dict(
            total=len(items),
            processed=sum(bool(i['prediction']) for i in items),
            reviewed=sum(self.review_count(i) == 2 for i in items),
            partial_review=sum(self.review_count(i) == 1 for i in items),
            unreviewed=sum(self.review_count(i) == 0 for i in items),
            truncated=sum(bool(i['prediction'] and i['prediction'].get('truncated')) for i in items),
            errors=sum(bool(i['error']) for i in items),
            sentiment=[dict(label_id=k,count=v) for k,v in sorted(sentiment.items())],
            topic=[dict(label_id=k,count=v) for k,v in sorted(topic.items())],
            cross=[dict(sentiment=k[0],topic=k[1],count=v) for k,v in sorted(cross.items())],
            denominator=dict(sentiment=sum(sentiment.values()),topic=sum(topic.values()),cross=sum(cross.values())),
            run_id=filters.get('run_id') or None,
            label_source=source,
            attention=attention,
            review_policy=review_policy,
            **snapshot,
        )

    def edit_text(self, item_id, text, expected_revision):
        check_text(text)
        with self.tx() as c:
            item = self.item(item_id, c=c)
            self._require_not_sensitivity_item(c, item_id)
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
            self._require_not_sensitivity_item(c, item_id)
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
                    prediction = json.loads(source['payload'], parse_constant=lambda _: None) if source else None
                    source_prediction_id = source['id'] if source else None
                    if not isinstance(prediction, dict) or prediction.get('schema_id') != dataset['schema_id']:
                        raise DomainError('CONFIRM_REQUIRES_PREDICTION', 'Dự đoán nguồn không khớp nội dung/schema hiện tại.', 409)
                elif status != 'confirmed' and 'source_prediction_id' in body:
                    # Explicit null clears provenance after a deliberate manual edit.
                    source_prediction_id = None
                task_pred = prediction.get(task) if isinstance(prediction, dict) else None
                if status == 'confirmed' and (not isinstance(prediction, dict) or prediction.get('schema_id') != dataset['schema_id'] or not isinstance(task_pred, dict) or task_pred.get('label_id') != label):
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
            self.require_dataset(c, dataset_id)
            self._require_not_sensitivity_dataset(c, dataset_id)
            items = self.query_items(dataset_id, filters, c)
            dataset = self.dataset(dataset_id, c)
            selected_run_id = filters.get('run_id') or self.latest_run_id(dataset_id,c)
            columns = ['item_id','source_row','text','metadata','revision_id','revision','schema_id','selected_run_id','prediction_status','prediction_id','run_id','model_id','model_version','label_source','selected_sentiment','selected_topic','ai_sentiment','ai_topic','sentiment_scores','topic_scores','reference_sentiment','reference_sentiment_source','reference_topic','reference_topic_source','review_sentiment','review_sentiment_status','review_sentiment_revision','review_sentiment_note','review_sentiment_source_prediction_id','review_topic','review_topic_status','review_topic_revision','review_topic_note','review_topic_source_prediction_id','effective_sentiment','effective_topic','token_count_before_truncation','truncated','warnings','error']
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader()
            for i in items:
                p = i['prediction'] if isinstance(i['prediction'], dict) else {}
                sp = p.get('sentiment') if isinstance(p.get('sentiment'), dict) else {}
                tp = p.get('topic') if isinstance(p.get('topic'), dict) else {}
                warnings_val = p.get('warnings') if isinstance(p.get('warnings'), list) else []
                ai_sentiment = sp['label_id'] if type(sp.get('label_id')) is int else ''
                ai_topic = tp['label_id'] if type(tp.get('label_id')) is int else ''
                s_scores = sp.get('scores') if isinstance(sp.get('scores'), list) else []
                t_scores = tp.get('scores') if isinstance(tp.get('scores'), list) else []
                row = dict(item_id=i['id'],source_row=i['source_row'],text=i['text'],metadata=encode(i['metadata']),revision_id=i['revision_id'],revision=i['revision'],schema_id=dataset['schema_id'],selected_run_id=selected_run_id or '',prediction_status='processed' if p else ('failed' if i['error'] else 'unprocessed'),prediction_id=p.get('id',''),run_id=p.get('run_id',''),model_id=p.get('model_id',''),model_version=p.get('model_version',''),ai_sentiment=ai_sentiment,ai_topic=ai_topic,sentiment_scores=encode(s_scores),topic_scores=encode(t_scores),effective_sentiment=i['effective']['sentiment'],effective_topic=i['effective']['topic'],token_count_before_truncation=p.get('token_count_before_truncation',''),truncated=bool(p.get('truncated',False)),warnings=encode(warnings_val),error=i['error'])
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
            filters_snapshot = dict(filters, review_policy=resolve_policy_metadata(dataset['schema_id']))
            c.execute('INSERT INTO exports VALUES(?,?,?,?,?,?,?,?)', (ident,dataset_id,selected_run_id,encode(filters_snapshot),encode(items),stream.getvalue().encode('utf-8-sig'),len(items),stamp))
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

    def _build_sensitivity_response(self, c, job_id, execution_resolver=None, _cached_identity=None):
        row = c.execute(
            """SELECT se.*,
                      j.run_id AS job_run_id,
                      j.status, j.completed, j.total, j.failed, j.cancel_requested, j.error AS job_error,
                      d.expires_at AS temp_expires_at,
                      si.current_revision_id AS source_current_revision_id,
                      br.text AS baseline_text,
                      vr.text AS variant_text
               FROM sensitivity_experiments se
               JOIN jobs j ON j.id=se.job_id
               JOIN datasets d ON d.id=se.temporary_dataset_id
               JOIN items bi ON bi.id=se.baseline_item_id
               JOIN revisions br ON br.id=bi.current_revision_id
               JOIN items vi ON vi.id=se.variant_item_id
               JOIN revisions vr ON vr.id=vi.current_revision_id
               LEFT JOIN items si ON si.id=se.source_item_id
               WHERE se.job_id=?""",
            (job_id,),
        ).fetchone()
        if not row:
            raise DomainError('NOT_FOUND', 'Không còn kết quả thử nghiệm tạm hoặc phản hồi nguồn.', 404)

        context = json.loads(row['context_json'])
        source = context['source']
        quick_source = None
        if context.get('source_kind') == 'quick':
            quick_source = self.validate_quick_source(c, context['source_job_id'], source['prediction_id'])
        sel = context['selection']
        execution = context['execution']
        attempt = context.get('attempt') or {}

        source_stale = True
        if row['source_current_revision_id'] == source['revision_id']:
            cur_rev = c.execute('SELECT text_hash FROM revisions WHERE id=?', (row['source_current_revision_id'],)).fetchone()
            if cur_rev and cur_rev['text_hash'] == source['text_sha256']:
                source_stale = False

        if _cached_identity is not None:
            active_model_changed = _cached_identity != execution
        elif execution_resolver is not None:
            try:
                current_identity = self._resolve_execution_identity(execution_resolver, execution['profile'])
            except DomainError as exc:
                if exc.code == 'MODEL_UNAVAILABLE':
                    current_identity = None
                else:
                    raise
            active_model_changed = bool(current_identity is not None and current_identity != execution)
        else:
            active_model_changed = False

        expiry = row['temp_expires_at']
        if quick_source is not None:
            source_expiry = quick_source['source_expires_at']
            expiry = min(expiry, source_expiry) if expiry is not None else source_expiry
        expires_at = None
        if expiry is not None:
            # ISO timestamps have microsecond precision. Truncate fractional units
            # so serialization never rounds the advertised lifetime above source TTL.
            seconds = math.floor(float(expiry))
            micros = int((float(expiry) - seconds) * 1_000_000)
            expires_at = datetime.fromtimestamp(seconds, timezone.utc).replace(
                microsecond=micros).isoformat().replace('+00:00', 'Z')

        status = row['status']
        attempt_error_code = attempt.get('error_code')
        if status in ('completed', 'queued', 'loading_model', 'running'):
            error = None
        elif status == 'cancelled':
            error = {'code': 'CANCELLED', 'message': row['job_error']} if row['job_error'] else None
        elif attempt_error_code:
            error_messages = {
                'MODEL_IDENTITY_CHANGED': 'Model active đã thay đổi so với lần thử nghiệm đã tạo.',
                'INVALID_PAIR_RESULT': 'Kết quả suy luận của cặp văn bản không hợp lệ.',
                'INFERENCE_FAILED': 'Không thể chạy suy luận trên model hiện tại.',
                'JOB_INTERRUPTED': 'Tiến trình suy luận bị gián đoạn trước khi hoàn tất.',
                'SOURCE_CONTEXT_CHANGED': 'Kết quả phân tích nguồn đã thay đổi. Phân tích lại câu để tiếp tục.',
            }
            error = {
                'code': attempt_error_code,
                'message': error_messages.get(attempt_error_code, row['job_error'] or 'Thử nghiệm không thể hoàn tất.'),
            }
        elif status == 'interrupted':
            error = {
                'code': 'JOB_INTERRUPTED',
                'message': row['job_error'] or 'Tiến trình suy luận bị gián đoạn trước khi hoàn tất.',
            }
        else:
            error = {
                'code': 'INFERENCE_FAILED',
                'message': row['job_error'] or 'Không thể chạy suy luận trên model hiện tại.',
            }

        result = None
        if status == 'completed':
            from services.sensitivity import build_sensitivity_result
            baseline_item = self.item(row['baseline_item_id'], row['job_run_id'], c=c)
            variant_item = self.item(row['variant_item_id'], row['job_run_id'], c=c)
            result = build_sensitivity_result(
                baseline_item,
                variant_item,
                profile_for(execution['profile']),
                context,
            )

        baseline_text = row['baseline_text']
        variant_text = row['variant_text']
        return {
            'experiment_id': job_id,
            'job_id': job_id,
            'status': status,
            'completed': row['completed'],
            'total': row['total'],
            'failed': row['failed'],
            'cancel_requested': bool(row['cancel_requested']),
            'source_stale': source_stale,
            'active_model_changed': active_model_changed,
            'source': source,
            'selection': {
                'start_utf16': sel['start_utf16'],
                'end_utf16': sel['end_utf16'],
                'text': baseline_text[sel['start_cp']:sel['end_cp']],
            },
            'baseline_text': baseline_text,
            'variant_text': variant_text,
            'execution': {
                **execution,
                'baseline_recomputed': True,
                'source_model_changed': bool(context.get('source_model_changed', False)),
            },
            'expires_at': expires_at,
            'error': error,
            'result': result,
        }

    def get_sensitivity_experiment(self, experiment_id, execution_resolver=None):
        with self.tx() as c:
            self.cleanup_expired_in_tx(c)
            return self._build_sensitivity_response(c, experiment_id, execution_resolver=execution_resolver)

    def create_sensitivity_experiment(self, item_id, body, idempotency_key, execution_resolver):
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise DomainError('VALIDATION_ERROR', 'Thiếu khóa Idempotency-Key hợp lệ.', 422)

        from services.sensitivity import validate_and_build_variant

        sel = body['selection']
        selected_run_id = body.get('run_id') or None
        idempotency_payload = {
            'item_id': item_id,
            'revision_id': body['revision_id'],
            'expected_revision': body['expected_revision'],
            'text_sha256': body['text_sha256'],
            'run_id': selected_run_id,
            'source_prediction_id': body.get('source_prediction_id'),
            'selection': {
                'start_utf16': sel['start_utf16'],
                'end_utf16': sel['end_utf16'],
                'text': sel['text'],
            },
        }

        with self.tx() as c:
            # 1. Reclaim expired temp experiments and idempotency/rate entries first.
            self.cleanup_expired_in_tx(c)

            # 2. Idempotency check BEFORE source currency/model/quota checks.
            prior = self.remember(c, idempotency_key, 'sensitivity', idempotency_payload)
            if prior:
                return self._build_sensitivity_response(c, prior, execution_resolver=execution_resolver)

            # 3. Durable items and explicitly marked quick sources are supported.
            row = c.execute(
                'SELECT i.id, i.dataset_id, i.current_revision_id, d.temporary, d.profile, d.schema_id '
                'FROM items i JOIN datasets d ON d.id=i.dataset_id WHERE i.id=?',
                (item_id,),
            ).fetchone()
            if not row:
                raise DomainError('NOT_FOUND', 'Không tìm thấy phản hồi.', 404)
            if row['temporary'] and c.execute(
                'SELECT 1 FROM sensitivity_experiments WHERE temporary_dataset_id=?', (row['dataset_id'],)
            ).fetchone():
                raise DomainError('INVALID_EXPERIMENT_SOURCE', 'Không thể lồng thử nghiệm độ nhạy.', 422)

            # 4. Validate optional run_id and resolve the viewed item.
            if selected_run_id:
                selected_run = self.run(selected_run_id, c)
                if selected_run['dataset_id'] != row['dataset_id']:
                    raise DomainError('RUN_DATASET_MISMATCH', 'Lần chạy không thuộc bộ phản hồi.', 422)
                resolved_run_id = selected_run_id
            else:
                resolved_run_id = self.latest_run_id(row['dataset_id'], c)
            view_item = self.item(item_id, selected_run_id, c)
            quick_source = None
            if row['temporary']:
                source_job = c.execute('SELECT id FROM jobs WHERE run_id=?', (resolved_run_id,)).fetchone()
                if not source_job:
                    raise DomainError('INVALID_EXPERIMENT_SOURCE', 'Nguồn tạm chưa có kết quả phân tích một câu.', 422)
                quick_source = self.validate_quick_source(c, source_job['id'], body.get('source_prediction_id'))
                if not body.get('source_prediction_id'):
                    raise DomainError('SOURCE_CONTEXT_CHANGED', 'Thiếu dự đoán nguồn của kết quả phân tích một câu.', 409)

            # 5. Check source revision currency and raw UTF-8 text hash.
            actual_text_sha256 = hashlib.sha256(view_item['text'].encode('utf-8')).hexdigest()
            if (
                view_item['stale']
                or view_item['revision_id'] != body['revision_id']
                or view_item['revision'] != body['expected_revision']
                or actual_text_sha256 != body['text_sha256']
            ):
                raise DomainError('REVISION_CONFLICT', 'Nội dung phản hồi đã thay đổi hoặc đang xem phiên bản cũ.', 409)

            # 6. Check source prediction identity in the viewed scope.
            view_prediction = view_item['prediction']
            view_pred_id = view_prediction['id'] if view_prediction else None
            if body.get('source_prediction_id') != view_pred_id:
                raise DomainError('SOURCE_CONTEXT_CHANGED', 'Dự đoán nguồn đã thay đổi. Tải lại trước khi thử nghiệm.', 409)

            # 7. Exact UTF-16 -> code point -> grapheme selection validation & variant build.
            variant_info = validate_and_build_variant(
                view_item['text'],
                sel['start_utf16'],
                sel['end_utf16'],
                sel['text'],
            )

            # 8. Enforce per-item, global concurrent (4), and global rate (10/60s) quotas atomically.
            existing = c.execute(
                """SELECT se.job_id FROM sensitivity_experiments se
                   JOIN jobs j ON j.id=se.job_id
                   WHERE se.source_item_id=?
                     AND j.status NOT IN ('completed','completed_with_errors','failed','cancelled','interrupted')
                   LIMIT 1""",
                (item_id,),
            ).fetchone()
            if existing:
                raise DomainError(
                    'EXPERIMENT_IN_PROGRESS',
                    'Phản hồi này đang có một thử nghiệm độ nhạy chưa kết thúc.',
                    409,
                    {'existing_job_id': existing['job_id']},
                )

            active_count = c.execute(
                """SELECT COUNT(*) FROM sensitivity_experiments se
                   JOIN jobs j ON j.id=se.job_id
                   WHERE j.status NOT IN ('completed','completed_with_errors','failed','cancelled','interrupted')"""
            ).fetchone()[0]
            if active_count >= 4:
                raise DomainError(
                    'EXPERIMENT_LIMIT',
                    'Đã đạt giới hạn 4 thử nghiệm độ nhạy đang chạy đồng thời.',
                    429,
                    {'limit': 4, 'reason': 'CONCURRENT_LIMIT'},
                )

            now_ts = time.time()
            rate_rows = c.execute(
                'SELECT created_ts FROM sensitivity_rate_limits WHERE created_ts>? ORDER BY created_ts ASC',
                (now_ts - 60.0,),
            ).fetchall()
            if len(rate_rows) >= 10:
                oldest_ts = float(rate_rows[0]['created_ts'])
                retry_after = max(1, math.ceil(oldest_ts + 60.0 - now_ts))
                raise DomainError(
                    'EXPERIMENT_LIMIT',
                    'Đã đạt giới hạn tối đa 10 lần tạo thử nghiệm trong một phút.',
                    429,
                    {'limit': 10, 'retry_after_seconds': retry_after, 'reason': 'RATE_LIMIT'},
                )

            # 9. Resolve and verify frozen model execution identity (no torch/inference load).
            identity = self._resolve_execution_identity(execution_resolver, row['profile'])
            if identity.get('schema_id') != row['schema_id']:
                raise DomainError('MODEL_UNAVAILABLE', 'Model không khớp schema của bộ phản hồi.', 409)

            # 10. Create temporary 2-item dataset, run, priority=1 job, experiment mapping, rate & idempotency atomically.
            temp_ds = self._create_dataset_tx(
                c,
                {
                    'name': 'Thử nghiệm độ nhạy',
                    'profile': row['profile'],
                    'items': [
                        {'text': variant_info['baseline_text']},
                        {'text': variant_info['variant_text']},
                    ],
                },
                temporary=True,
            )
            temp_items = c.execute(
                'SELECT id FROM items WHERE dataset_id=? ORDER BY source_row ASC',
                (temp_ds['id'],),
            ).fetchall()
            baseline_item_id = temp_items[0]['id']
            variant_item_id = temp_items[1]['id']

            run = self._create_run_tx(
                c,
                temp_ds['id'],
                {
                    'available': True,
                    'schema_id': identity['schema_id'],
                    'model_id': identity['model_id'],
                    'model_version': identity['model_version'],
                },
                allow_sensitivity=True,
            )

            source_model_changed = False
            if view_prediction is not None:
                source_model_changed = (
                    view_prediction.get('model_id'),
                    view_prediction.get('model_version'),
                    view_prediction.get('schema_id'),
                ) != (
                    identity['model_id'],
                    identity['model_version'],
                    identity['schema_id'],
                )

            context_obj = {
                'schema_version': 1,
                'source_kind': 'quick' if quick_source else 'dataset',
                'source_job_id': quick_source['job']['id'] if quick_source else None,
                'source': {
                    'item_id': item_id,
                    'revision_id': view_item['revision_id'],
                    'revision': view_item['revision'],
                    'text_sha256': actual_text_sha256,
                    'selected_run_id': selected_run_id,
                    'resolved_run_id': resolved_run_id,
                    'prediction_id': view_pred_id,
                },
                'selection': {
                    'start_utf16': variant_info['start_utf16'],
                    'end_utf16': variant_info['end_utf16'],
                    'start_cp': variant_info['start_cp'],
                    'end_cp': variant_info['end_cp'],
                    'text_sha256': hashlib.sha256(sel['text'].encode('utf-8')).hexdigest(),
                    'variant_sha256': variant_info['variant_sha256'],
                },
                'execution': identity,
                'source_model_changed': source_model_changed,
                'request_hash': hashlib.sha256(encode(idempotency_payload).encode()).hexdigest(),
                'attempt': {
                    'error_code': None,
                    'model_input_equal': None,
                },
            }

            c.execute(
                'INSERT INTO sensitivity_experiments VALUES(?,?,?,?,?,?,?,?,?)',
                (
                    run['job_id'],
                    temp_ds['id'],
                    row['dataset_id'],
                    item_id,
                    view_item['revision_id'],
                    baseline_item_id,
                    variant_item_id,
                    encode(context_obj),
                    now(),
                ),
            )
            c.execute('INSERT INTO sensitivity_rate_limits VALUES(?,?)', (uid(), now_ts))
            self.remember(c, idempotency_key, 'sensitivity', idempotency_payload, run['job_id'])
            return self._build_sensitivity_response(c, run['job_id'], _cached_identity=identity)
