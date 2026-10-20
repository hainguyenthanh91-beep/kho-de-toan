"""Kho dữ liệu. Hiện dùng SQLite (một file kho.db); các câu lệnh viết theo SQL chuẩn để sau này
chuyển lên cơ sở dữ liệu đám mây (PostgreSQL) chỉ cần thay lớp kết nối này."""
import json, os, re, sqlite3, threading, time
from pathlib import Path

DATA_DIR = Path(os.environ.get('KHODE_DATA', Path(__file__).resolve().parent.parent / 'du_lieu'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'kho.db'
SCHEMA_VERSION = 2

_local = threading.local()
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_id INTEGER REFERENCES folders(id),
  kind TEXT NOT NULL,              -- 'cd' = cây chuyên đề, 'de' = tổng hợp đề thi
  name TEXT NOT NULL,
  code TEXT,
  pos INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_folder_code ON folders(code) WHERE code IS NOT NULL AND code != '';
CREATE INDEX IF NOT EXISTS ix_folder_parent ON folders(parent_id);
CREATE TABLE IF NOT EXISTS exam_sets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  folder_id INTEGER REFERENCES folders(id),
  title TEXT NOT NULL,
  source TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  folder_id INTEGER REFERENCES folders(id),
  set_id INTEGER REFERENCES exam_sets(id),
  set_pos INTEGER,
  set_part INTEGER,
  level TEXT NOT NULL DEFAULT '',
  qtype TEXT NOT NULL,
  answer TEXT,
  data TEXT NOT NULL,
  plain TEXT NOT NULL DEFAULT '',
  fingerprint TEXT,
  source TEXT,
  has_solution INTEGER NOT NULL DEFAULT 0,
  warnings TEXT,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_q_folder ON questions(folder_id, qtype, level);
CREATE INDEX IF NOT EXISTS ix_q_set ON questions(set_id, set_pos);
CREATE INDEX IF NOT EXISTS ix_q_fp ON questions(fingerprint);
CREATE TABLE IF NOT EXISTS media (hash TEXT PRIMARY KEY, ext TEXT NOT NULL, data BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS exams (
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created_at REAL NOT NULL, config TEXT, n_questions INTEGER);
CREATE TABLE IF NOT EXISTS usage (
  question_id INTEGER NOT NULL, exam_id INTEGER NOT NULL, used_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_usage_q ON usage(question_id, used_at);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""

def _old_schema(c):
    cols = {r[1] for r in c.execute("PRAGMA table_info(questions)")}
    return bool(cols) and 'folder_id' not in cols

def conn():
    c = getattr(_local, 'c', None)
    if c is None:
        with _lock:
            if DB_PATH.exists():
                t = sqlite3.connect(DB_PATH)
                old = _old_schema(t)
                t.close()
                if old:  # kho của bản cũ: cất sang file sao lưu, bắt đầu kho mới
                    stamp = time.strftime('%Y%m%d_%H%M%S')
                    for suf in ('', '-wal', '-shm'):
                        p = Path(str(DB_PATH) + suf)
                        if p.exists():
                            p.rename(DATA_DIR / f'kho_ban_cu_{stamp}.db{suf}')
            c = sqlite3.connect(DB_PATH, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript(SCHEMA)
            if not c.execute('SELECT 1 FROM folders LIMIT 1').fetchone():
                seed_folders(c)
            _local.c = c
    return c

def seed_folders(c):
    data = json.loads((Path(__file__).resolve().parent / 'cay_mac_dinh.json').read_text(encoding='utf-8'))
    for gi, g in enumerate(data['chuyen_de']):
        gid = c.execute('INSERT INTO folders(parent_id, kind, name, code, pos) VALUES (NULL,?,?,?,?)',
                        ('cd', g['ten'], g['ma'], gi)).lastrowid
        for ci, ch in enumerate(g['con']):
            ccode = f'{g["ma"]}.{ch["ma"]}'
            cid = c.execute('INSERT INTO folders(parent_id, kind, name, code, pos) VALUES (?,?,?,?,?)',
                            (gid, 'cd', ch['ten'], ccode, ci)).lastrowid
            for bi, b in enumerate(ch['con']):
                m = re.match(r'Bài\s+(\d+)', b)
                bcode = f'{ccode}.B{m.group(1)}' if m else None
                c.execute('INSERT INTO folders(parent_id, kind, name, code, pos) VALUES (?,?,?,?,?)', (cid, 'cd', b, bcode, bi))
    for gi, g in enumerate(data['de_thi']):
        gid = c.execute('INSERT INTO folders(parent_id, kind, name, code, pos) VALUES (NULL,?,?,NULL,?)', ('de', g['ten'], gi)).lastrowid
        for ci, ch in enumerate(g['con']):
            c.execute('INSERT INTO folders(parent_id, kind, name, code, pos) VALUES (?,?,?,NULL,?)', (gid, 'de', ch, ci))
    c.commit()

# ------------------------------------------------------------------ thư mục

def all_folders():
    return [dict(r) for r in conn().execute('SELECT * FROM folders ORDER BY pos, id')]

def subtree_ids(fid):
    rows = conn().execute('SELECT id, parent_id FROM folders').fetchall()
    kids = {}
    for r in rows:
        kids.setdefault(r['parent_id'], []).append(r['id'])
    out, stack = [], [fid]
    while stack:
        x = stack.pop()
        out.append(x)
        stack.extend(kids.get(x, []))
    return out

def folder_by_code(code):
    if not code:
        return None
    r = conn().execute('SELECT id FROM folders WHERE lower(code) = lower(?)', (code.strip(),)).fetchone()
    return r['id'] if r else None

def folder_path(fid):
    names = []
    seen = set()
    while fid and fid not in seen:
        seen.add(fid)
        r = conn().execute('SELECT name, parent_id FROM folders WHERE id=?', (fid,)).fetchone()
        if not r:
            break
        names.append(r['name'])
        fid = r['parent_id']
    return ' › '.join(reversed(names))

# ------------------------------------------------------------------ hình, câu hỏi

def save_media(media):
    conn().executemany('INSERT OR IGNORE INTO media(hash, ext, data) VALUES (?,?,?)',
                       [(h, ext, blob) for h, (blob, ext) in media.items()])

def load_media(h):
    row = conn().execute('SELECT data, ext FROM media WHERE hash=?', (h,)).fetchone()
    return (row['data'], row['ext']) if row else (None, None)

def insert_question(q):
    data = {k: q.get(k) for k in ('stem', 'options', 'items', 'solution', 'rels')}
    cur = conn().execute(
        'INSERT INTO questions(folder_id, set_id, set_pos, set_part, level, qtype, answer, data, plain, fingerprint, source,'
        ' has_solution, warnings, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (q.get('folder_id'), q.get('set_id'), q.get('set_pos'), q.get('set_part'), q.get('level') or '', q['qtype'],
         q.get('answer'), json.dumps(data, ensure_ascii=False), q.get('plain', ''), q.get('fingerprint'), q.get('source'),
         1 if q.get('solution') else 0, json.dumps(q.get('warnings') or [], ensure_ascii=False), time.time()))
    return cur.lastrowid

def row_to_q(row):
    q = dict(row)
    q.update(json.loads(row['data']))
    q.pop('data', None)
    q['warnings'] = json.loads(row['warnings'] or '[]')
    return q

def get_question(qid):
    row = conn().execute('SELECT * FROM questions WHERE id=?', (qid,)).fetchone()
    return row_to_q(row) if row else None

def fingerprints_exist(fps):
    out, fps = set(), list(fps)
    for i in range(0, len(fps), 500):
        chunk = fps[i:i + 500]
        rows = conn().execute(f'SELECT fingerprint FROM questions WHERE fingerprint IN ({",".join("?" * len(chunk))})', chunk)
        out.update(r[0] for r in rows)
    return out

def get_setting(key, default=None):
    row = conn().execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default

def set_setting(key, value):
    conn().execute('INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   (key, json.dumps(value, ensure_ascii=False)))
    conn().commit()
