"""Máy chủ web của phần mềm Kho Đề Toán."""
import io, json, re, secrets, sqlite3, time, unicodedata, zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import db, docx_io, mathtype_convert

APP_DIR = Path(__file__).resolve().parent
STATIC = APP_DIR / 'static'
EXAM_DIR = db.DATA_DIR / 'de_da_tao'
EXAM_DIR.mkdir(exist_ok=True)
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
ORDER = ['TN', 'ĐS', 'TLN', 'TL']

app = FastAPI(title='Kho Đề Toán')
PENDING = {}  # phiên nhập đang xem trước

def norm(s):
    s = (s or '').lower().replace('đ', 'd')
    s = unicodedata.normalize('NFD', s)
    return ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')

def media_loader(h):
    data, _ = db.load_media(h)
    if data is None:
        raise HTTPException(500, f'Thiếu dữ liệu hình {h}')
    return data

def safe_name(s):
    return re.sub(r'[^\w\-]+', '_', norm(s)).strip('_')[:60] or 'de'

# ================================================================== cây thư mục

@app.get('/api/folders')
def api_folders(kind: str = 'cd'):
    c = db.conn()
    fs = [f for f in db.all_folders() if f['kind'] == kind]
    kids = {}
    for f in fs:
        kids.setdefault(f['parent_id'], []).append(f)
    own, sets_by_folder = {}, {}
    if kind == 'cd':
        for r in c.execute('SELECT folder_id, COUNT(*) n FROM questions WHERE folder_id IS NOT NULL GROUP BY folder_id'):
            own[r['folder_id']] = r['n']
    else:
        for r in c.execute('SELECT s.id, s.folder_id, s.title, (SELECT COUNT(*) FROM questions q WHERE q.set_id = s.id) n '
                           'FROM exam_sets s ORDER BY s.title'):
            sets_by_folder.setdefault(r['folder_id'], []).append({'id': r['id'], 'title': r['title'], 'n': r['n']})
            own[r['folder_id']] = own.get(r['folder_id'], 0) + 1

    def build(f):
        ch = [build(k) for k in kids.get(f['id'], [])]
        node = {'id': f['id'], 'name': f['name'], 'code': f['code'], 'parent_id': f['parent_id'], 'children': ch,
                'count': own.get(f['id'], 0) + sum(x['count'] for x in ch)}
        if kind == 'de':
            node['sets'] = sets_by_folder.get(f['id'], [])
        return node
    tree = [build(f) for f in kids.get(None, [])]
    out = {'tree': tree}
    if kind == 'cd':
        out['total'] = c.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
        out['unclassified'] = c.execute('SELECT COUNT(*) FROM questions WHERE folder_id IS NULL').fetchone()[0]
    else:
        out['total'] = c.execute('SELECT COUNT(*) FROM exam_sets').fetchone()[0]
        out['loose'] = sets_by_folder.get(None, [])
    return out

def _auto_code(c, parent):
    if not parent or not parent['code']:
        return None
    base = parent['code']
    n = c.execute('SELECT COUNT(*) FROM folders WHERE parent_id=?', (parent['id'],)).fetchone()[0] + 1
    prefix = 'D' if re.search(r'\.B\d+$', base) else ''
    while c.execute('SELECT 1 FROM folders WHERE lower(code)=lower(?)', (f'{base}.{prefix}{n}',)).fetchone():
        n += 1
    return f'{base}.{prefix}{n}'

@app.get('/api/folders/codes')
def api_folder_codes():
    """Danh sách mã chuyên đề (để dán cho Claude khi chuẩn hoá đề, điền bảng PHÂN LOẠI)."""
    fs = [f for f in db.all_folders() if f['kind'] == 'cd']
    kids = {}
    for f in fs:
        kids.setdefault(f['parent_id'], []).append(f)
    lines = ['# DANH SÁCH MÃ CHUYÊN ĐỀ — Kho Đề Toán', '# Dùng cột "Mã chuyên đề" trong bảng PHÂN LOẠI. Mức: M1 Nhận biết, M2 Thông hiểu, M3 Vận dụng, M4 Vận dụng cao.', '']
    def walk(pid, depth):
        for f in kids.get(pid, []):
            lines.append('  ' * depth + (f'{f["code"]}  ' if f['code'] else '') + f['name'])
            walk(f['id'], depth + 1)
    walk(None, 0)
    data = '\n'.join(lines) + '\n'
    return Response(data.encode('utf-8'), media_type='text/plain; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="Ma_chuyen_de.txt"'})

@app.post('/api/folders')
def api_folder_create(body: dict = Body(...)):
    c = db.conn()
    name = (body.get('name') or '').strip()
    if not name:
        raise HTTPException(400, 'Chưa nhập tên thư mục')
    kind = body.get('kind') or 'cd'
    pid = body.get('parent_id')
    parent = c.execute('SELECT * FROM folders WHERE id=?', (pid,)).fetchone() if pid else None
    if pid and (not parent or parent['kind'] != kind):
        raise HTTPException(400, 'Thư mục cha không hợp lệ')
    code = (body.get('code') or '').strip() or (_auto_code(c, parent) if kind == 'cd' else None)
    pos = c.execute('SELECT COALESCE(MAX(pos), -1) + 1 FROM folders WHERE parent_id IS ?', (pid,)).fetchone()[0]
    try:
        fid = c.execute('INSERT INTO folders(parent_id, kind, name, code, pos) VALUES (?,?,?,?,?)',
                        (pid, kind, name, code, pos)).lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(400, f'Mã “{code}” đã có thư mục khác dùng')
    c.commit()
    return {'id': fid, 'code': code}

@app.patch('/api/folders/{fid}')
def api_folder_update(fid: int, body: dict = Body(...)):
    c = db.conn()
    f = c.execute('SELECT * FROM folders WHERE id=?', (fid,)).fetchone()
    if not f:
        raise HTTPException(404)
    fields, args = [], []
    if 'name' in body:
        if not body['name'].strip():
            raise HTTPException(400, 'Tên không được để trống')
        fields.append('name=?'); args.append(body['name'].strip())
    if 'code' in body:
        fields.append('code=?'); args.append((body['code'] or '').strip() or None)
    if 'parent_id' in body:
        pid = body['parent_id']
        if pid is not None:
            if pid in db.subtree_ids(fid):
                raise HTTPException(400, 'Không thể chuyển thư mục vào chính nó')
            p = c.execute('SELECT kind FROM folders WHERE id=?', (pid,)).fetchone()
            if not p or p['kind'] != f['kind']:
                raise HTTPException(400, 'Thư mục đích không hợp lệ')
        fields += ['parent_id=?', 'pos=?']
        args += [pid, c.execute('SELECT COALESCE(MAX(pos), -1) + 1 FROM folders WHERE parent_id IS ?', (pid,)).fetchone()[0]]
    if not fields:
        return {'ok': True}
    try:
        c.execute(f'UPDATE folders SET {", ".join(fields)} WHERE id=?', args + [fid])
    except sqlite3.IntegrityError:
        raise HTTPException(400, 'Mã này đã có thư mục khác dùng')
    c.commit()
    return {'ok': True}

@app.post('/api/folders/{fid}/move')
def api_folder_move(fid: int, body: dict = Body(...)):
    """Đổi thứ tự: đặt thư mục ngay trước/sau một thư mục cùng cha."""
    c = db.conn()
    f = c.execute('SELECT * FROM folders WHERE id=?', (fid,)).fetchone()
    sib = [r['id'] for r in c.execute('SELECT id FROM folders WHERE parent_id IS ? ORDER BY pos, id', (f['parent_id'],))]
    i = sib.index(fid)
    j = max(0, min(len(sib) - 1, i + (1 if body.get('dir') == 'down' else -1)))
    sib.insert(j, sib.pop(i))
    c.executemany('UPDATE folders SET pos=? WHERE id=?', [(k, x) for k, x in enumerate(sib)])
    c.commit()
    return {'ok': True}

@app.delete('/api/folders/{fid}')
def api_folder_delete(fid: int):
    c = db.conn()
    f = c.execute('SELECT * FROM folders WHERE id=?', (fid,)).fetchone()
    if not f:
        raise HTTPException(404)
    ids = db.subtree_ids(fid)
    ph = ','.join('?' * len(ids))
    nq = c.execute(f'UPDATE questions SET folder_id=? WHERE folder_id IN ({ph})', [f['parent_id']] + ids).rowcount
    ns = c.execute(f'UPDATE exam_sets SET folder_id=? WHERE folder_id IN ({ph})', [f['parent_id']] + ids).rowcount
    c.execute(f'DELETE FROM folders WHERE id IN ({ph})', ids)
    c.commit()
    return {'moved_questions': nq, 'moved_sets': ns}

# ================================================================== lọc câu hỏi

def build_filter(folder=None, level=None, qtype=None, text=None, avoid_days=0, need_solution=False, exclude=None,
                 no_answer=False, set_id=None, scope='cd', unclassified=False):
    where, args = [], []
    if set_id:
        where.append('set_id = ?'); args.append(set_id)
    elif scope == 'de':
        if folder:
            ids = db.subtree_ids(int(folder))
            where.append(f'set_id IN (SELECT id FROM exam_sets WHERE folder_id IN ({",".join("?" * len(ids))}))'); args += ids
        else:
            where.append('set_id IS NOT NULL')
    elif unclassified:
        where.append('folder_id IS NULL')
    elif folder:
        ids = db.subtree_ids(int(folder))
        where.append(f'folder_id IN ({",".join("?" * len(ids))})'); args += ids
    if level:
        lv = [x for x in str(level).split(',') if x]
        where.append(f'level IN ({",".join("?" * len(lv))})'); args += lv
    if qtype:
        ty = [x for x in str(qtype).split(',') if x]
        where.append(f'qtype IN ({",".join("?" * len(ty))})'); args += ty
    if text:
        for word in norm(text).split():
            where.append('plain LIKE ?'); args.append(f'%{word}%')
    if avoid_days:
        where.append('id NOT IN (SELECT question_id FROM usage WHERE used_at > ?)')
        args.append(time.time() - avoid_days * 86400)
    if need_solution:
        where.append('has_solution = 1')
    if no_answer:
        where.append("(answer IS NULL OR answer = '' OR answer LIKE '%?%') AND qtype != 'TL'")
    if exclude:
        where.append(f'id NOT IN ({",".join("?" * len(exclude))})'); args += list(exclude)
    return (' WHERE ' + ' AND '.join(where)) if where else '', args

def _filter_from(p):
    return build_filter(p.get('folder'), p.get('level'), p.get('qtype'), p.get('q'), int(p.get('avoid_days') or 0),
                        no_answer=bool(int(p.get('no_answer') or 0)), set_id=p.get('set'), scope=p.get('scope') or 'cd',
                        unclassified=bool(int(p.get('unclassified') or 0)))

@app.get('/api/questions')
def api_questions(folder: Optional[int] = None, set: Optional[int] = None, scope: str = 'cd', unclassified: int = 0,
                  level: Optional[str] = None, qtype: Optional[str] = None, q: Optional[str] = None, avoid_days: int = 0,
                  no_answer: int = 0, page: int = 1, size: int = 20, sort: str = 'tree'):
    where, args = _filter_from(locals())
    c = db.conn()
    total = c.execute('SELECT COUNT(*) FROM questions' + where, args).fetchone()[0]
    if set or scope == 'de':
        order = 'set_id, set_part, set_pos, id'
    else:
        order = {'new': 'id DESC', 'least_used': 'used ASC, id DESC'}.get(sort, 'folder_id IS NULL, folder_id, id')
    rows = c.execute('SELECT *, (SELECT COUNT(*) FROM usage u WHERE u.question_id = questions.id) used,'
                     ' (SELECT COUNT(*) FROM questions q2 WHERE q2.set_id = questions.set_id AND q2.set_part IS questions.set_part'
                     '  AND q2.set_pos <= questions.set_pos) part_no FROM questions'
                     + where + f' ORDER BY {order} LIMIT ? OFFSET ?', args + [size, (max(page, 1) - 1) * size]).fetchall()
    fcode = {f['id']: f['code'] or f['name'] for f in db.all_folders()}
    items = []
    for r in rows:
        qq = db.row_to_q(r)
        parts = docx_io.question_parts(qq, with_solution=False)
        items.append({'id': r['id'], 'folder_id': r['folder_id'], 'code': fcode.get(r['folder_id'], ''), 'level': r['level'],
                      'qtype': r['qtype'], 'used': r['used'], 'answer': r['answer'], 'has_solution': bool(r['has_solution']),
                      'set_id': r['set_id'], 'set_pos': r['set_pos'], 'set_part': r['set_part'], 'part_no': r['part_no'], 'stem': parts['stem']})
    return {'total': total, 'page': page, 'size': size, 'items': items}

@app.get('/api/stats')
def api_stats(folder: Optional[int] = None, set: Optional[int] = None, scope: str = 'cd', unclassified: int = 0,
              q: Optional[str] = None, avoid_days: int = 0):
    where, args = _filter_from({'folder': folder, 'set': set, 'scope': scope, 'unclassified': unclassified, 'q': q,
                                'avoid_days': avoid_days})
    c = db.conn()
    lv = {r[0]: r[1] for r in c.execute('SELECT level, COUNT(*) FROM questions' + where + ' GROUP BY level', args)}
    ty = {r[0]: r[1] for r in c.execute('SELECT qtype, COUNT(*) FROM questions' + where + ' GROUP BY qtype', args)}
    no_ans = c.execute('SELECT COUNT(*) FROM questions' + (where + ' AND' if where else ' WHERE') +
                       " (answer IS NULL OR answer = '' OR answer LIKE '%?%') AND qtype != 'TL'", args).fetchone()[0]
    return {'level': lv, 'type': ty, 'total': sum(ty.values()), 'no_answer': no_ans}

@app.get('/api/questions/{qid}')
def api_question(qid: int):
    q = db.get_question(qid)
    if not q:
        raise HTTPException(404, 'Không tìm thấy câu hỏi')
    c = db.conn()
    uses = c.execute('SELECT e.title, u.used_at FROM usage u JOIN exams e ON e.id = u.exam_id WHERE u.question_id=? '
                     'ORDER BY u.used_at DESC', (qid,)).fetchall()
    st = c.execute('SELECT id, title FROM exam_sets WHERE id=?', (q['set_id'],)).fetchone() if q['set_id'] else None
    f = c.execute('SELECT code FROM folders WHERE id=?', (q['folder_id'],)).fetchone() if q['folder_id'] else None
    return {'id': qid, 'folder_id': q['folder_id'], 'code': f['code'] if f else '', 'folder_path': db.folder_path(q['folder_id']) or 'Chưa phân loại',
            'level': q['level'], 'qtype': q['qtype'], 'answer': q['answer'], 'source': q['source'], 'warnings': q['warnings'],
            'set': {'id': st['id'], 'title': st['title']} if st else None,
            'uses': [{'exam': u['title'], 'at': datetime.fromtimestamp(u['used_at']).strftime('%d/%m/%Y')} for u in uses],
            'parts': docx_io.question_parts(q, with_solution=True)}

def check_answer(qtype, a, n_items=4):
    a = (a or '').strip()
    if qtype == 'TN' and a not in ('A', 'B', 'C', 'D', ''):
        raise HTTPException(400, 'Đáp án trắc nghiệm phải là A, B, C hoặc D')
    if qtype == 'ĐS':
        a = a.upper().replace('D', 'Đ')
        if a and not re.fullmatch(r'[ĐS?]{%d}' % n_items, a):
            raise HTTPException(400, 'Đáp án Đúng/Sai phải gồm Đ hoặc S cho từng ý')
    if qtype == 'TLN' and len(a) > 6:
        raise HTTPException(400, 'Đáp án trả lời ngắn tối đa 6 kí tự')
    return a or None

@app.patch('/api/questions/{qid}')
def api_update(qid: int, body: dict = Body(...)):
    c = db.conn()
    fields, args = [], []
    if 'folder_id' in body:
        fields.append('folder_id=?'); args.append(body['folder_id'] or None)
    if 'level' in body:
        fields.append('level=?'); args.append(body['level'] if body['level'] in ('M1', 'M2', 'M3', 'M4') else '')
    if 'answer' in body:
        q = db.get_question(qid)
        fields.append('answer=?'); args.append(check_answer(q['qtype'], body['answer'], len(q.get('items') or []) or 4))
    if fields:
        c.execute(f'UPDATE questions SET {", ".join(fields)} WHERE id=?', args + [qid])
        c.commit()
    return {'ok': True}

@app.post('/api/questions/bulk')
def api_bulk(body: dict = Body(...)):
    """Gán chuyên đề / mức cho nhiều câu một lúc."""
    ids = [int(x) for x in body.get('ids') or []]
    if not ids:
        return {'n': 0}
    c = db.conn()
    ph = ','.join('?' * len(ids))
    if 'folder_id' in body:
        c.execute(f'UPDATE questions SET folder_id=? WHERE id IN ({ph})', [body['folder_id'] or None] + ids)
    if 'level' in body:
        c.execute(f'UPDATE questions SET level=? WHERE id IN ({ph})', [body['level'] or ''] + ids)
    c.commit()
    return {'n': len(ids)}

@app.delete('/api/questions/{qid}')
def api_delete(qid: int):
    c = db.conn()
    c.execute('DELETE FROM usage WHERE question_id=?', (qid,))
    c.execute('DELETE FROM questions WHERE id=?', (qid,))
    c.commit()
    return {'ok': True}

@app.get('/api/questions/{qid}/docx')
def api_question_docx(qid: int):
    q = db.get_question(qid)
    if not q:
        raise HTTPException(404)
    b = docx_io.DocBuilder(media_loader)
    code = db.conn().execute('SELECT code FROM folders WHERE id=?', (q['folder_id'],)).fetchone() if q['folder_id'] else None
    b.add(b.para([b.run(f'[{code["code"] if code else ""}] [{q["level"]}] [{q["qtype"]}]', b=True, color='1F4E79')]))
    docx_io.place_question(b, q, 'Câu 1.', show_key=True, solution=True)
    return Response(b.save(), media_type=DOCX_MIME, headers={'Content-Disposition': f'attachment; filename="cau_{qid}.docx"'})

@app.get('/media/{name}')
def api_media(name: str):
    h = name.split('.')[0]
    data, ext = db.load_media(h)
    if data is None:
        for p in PENDING.values():
            if h in p['media']:
                data, ext = p['media'][h]
                break
    if data is None:
        raise HTTPException(404)
    return Response(data, media_type=docx_io.CT_DEFAULTS.get(ext, 'application/octet-stream'),
                    headers={'Cache-Control': 'max-age=31536000'})

# ================================================================== đề trong Tổng hợp đề thi

def set_parts(set_id):
    rows = db.conn().execute('SELECT id FROM questions WHERE set_id=? ORDER BY set_part, set_pos, id', (set_id,)).fetchall()
    qs = [db.get_question(r['id']) for r in rows]
    parts = []
    for q in qs:
        key = (q.get('set_part') or 0, q['qtype'])
        if not parts or parts[-1][0] != key:
            parts.append((key, []))
        parts[-1][1].append(q)
    return [(k[1], v) for k, v in parts]

@app.get('/api/sets/{sid}')
def api_set(sid: int):
    c = db.conn()
    s = c.execute('SELECT * FROM exam_sets WHERE id=?', (sid,)).fetchone()
    if not s:
        raise HTTPException(404)
    n = c.execute('SELECT qtype, COUNT(*) n FROM questions WHERE set_id=? GROUP BY qtype', (sid,)).fetchall()
    return {'id': sid, 'title': s['title'], 'folder_id': s['folder_id'], 'folder_path': db.folder_path(s['folder_id']),
            'source': s['source'], 'counts': {r['qtype']: r['n'] for r in n},
            'created': datetime.fromtimestamp(s['created_at']).strftime('%d/%m/%Y')}

@app.patch('/api/sets/{sid}')
def api_set_update(sid: int, body: dict = Body(...)):
    c = db.conn()
    if 'title' in body and body['title'].strip():
        c.execute('UPDATE exam_sets SET title=? WHERE id=?', (body['title'].strip(), sid))
    if 'folder_id' in body:
        c.execute('UPDATE exam_sets SET folder_id=? WHERE id=?', (body['folder_id'], sid))
    c.commit()
    return {'ok': True}

@app.delete('/api/sets/{sid}')
def api_set_delete(sid: int, with_questions: int = 1):
    c = db.conn()
    if with_questions:
        ids = [r['id'] for r in c.execute('SELECT id FROM questions WHERE set_id=?', (sid,))]
        if ids:
            ph = ','.join('?' * len(ids))
            c.execute(f'DELETE FROM usage WHERE question_id IN ({ph})', ids)
            c.execute(f'DELETE FROM questions WHERE id IN ({ph})', ids)
    else:
        c.execute('UPDATE questions SET set_id=NULL, set_pos=NULL, set_part=NULL WHERE set_id=?', (sid,))
    c.execute('DELETE FROM exam_sets WHERE id=?', (sid,))
    c.commit()
    return {'ok': True}

@app.get('/api/sets/{sid}/docx')
def api_set_docx(sid: int, solution: int = 1):
    s = api_set(sid)
    parts = [(t, [(q, [0, 1, 2, 3]) for q in qs]) for t, qs in set_parts(sid)]
    info = {'title': s['title'], 'center': db.get_setting('center', ''), 'minutes': ''}
    data = docx_io.build_exam(media_loader, info, {'code': '', 'parts': parts}, solution=bool(solution))
    fname = safe_name(s['title']) + ('_loi_giai' if solution else '') + '.docx'
    return Response(data, media_type=DOCX_MIME, headers={'Content-Disposition': f'attachment; filename="{fname}"'})

# ================================================================== nhập liệu

@app.post('/api/import/preview')
async def api_import_preview(files: list[UploadFile] = File(...)):
    for k in [k for k, v in PENDING.items() if time.time() - v['time'] > 3600]:
        PENDING.pop(k, None)
    token = secrets.token_hex(8)
    out, store, media = [], [], {}
    for f in files:
        data = await f.read()
        name = f.filename or 'file.docx'
        if not name.lower().endswith('.docx'):
            out.append({'file': name, 'error': 'Chỉ nhận file .docx (file .doc cũ hãy mở bằng Word rồi Lưu thành .docx; PDF hãy chuyển sang Word trước)'})
            continue
        n_mt = 0
        try:
            if mathtype_convert.count_mathtype(data):
                data, st = mathtype_convert.convert_docx(data)
                n_mt = st['converted']
                mt_failed = st['failed']
            res = docx_io.parse_docx(data, name)
        except Exception as e:
            out.append({'file': name, 'error': f'Không đọc được file: {e}'})
            continue
        media.update(res.media)
        fps = db.fingerprints_exist({q['fingerprint'] for q in res.questions})
        seen, qs = set(), []
        for q in res.questions:
            dup = q['fingerprint'] in fps or q['fingerprint'] in seen
            seen.add(q['fingerprint'])
            q['duplicate'] = dup
            q['file'] = name
            q['folder_id'] = db.folder_by_code(q['code'])
            if q['code'] and not q['folder_id']:
                q['warnings'].append(f'Mã “{q["code"]}” chưa có trong cây thư mục')
            idx = len(store)
            store.append(q)
            qs.append({'idx': idx, 'no': q['no_in_file'], 'num': q.get('num_in_file'), 'part': q.get('part_in_file'),
                       'folder_id': q['folder_id'], 'level': q['level'], 'qtype': q['qtype'], 'answer': q['answer'],
                       'warnings': q['warnings'], 'duplicate': dup, 'parts': docx_io.question_parts(q, with_solution=True)})
        title = re.sub(r'\.docx$', '', name, flags=re.I).replace('_', ' ').strip()
        warns = list(res.warnings)
        if res.classified is not None:
            nf = sum(1 for q in res.questions if q.get('folder_id'))
            warns.insert(0, f'Đã đọc bảng PHÂN LOẠI: {res.classified}/{len(res.questions)} câu có mã chuyên đề và mức độ'
                         + (f', {nf} câu đã khớp thư mục.' if nf == res.classified else f'; {res.classified - nf} mã chưa có trong cây thư mục.'))
        if n_mt:
            warns.insert(0, f'Đã tự đổi {n_mt} công thức MathType sang Equation.' +
                         (f' {mt_failed} công thức không đổi được, vẫn giữ dạng MathType.' if mt_failed else ''))
        out.append({'file': name, 'title': title, 'warnings': warns, 'info': bool(n_mt), 'questions': qs})
    PENDING[token] = {'time': time.time(), 'questions': store, 'media': media}
    return {'token': token, 'files': out}

@app.post('/api/import/commit')
def api_import_commit(body: dict = Body(...)):
    p = PENDING.pop(body.get('token'), None)
    if not p:
        raise HTTPException(400, 'Phiên nhập đã hết hạn, hãy chọn lại file.')
    edits = {int(k): v for k, v in (body.get('edits') or {}).items()}
    skip = set(int(x) for x in body.get('skip') or [])
    as_exam = body.get('as_exam') or {}
    c = db.conn()
    db.save_media(p['media'])
    set_ids = {}
    if as_exam.get('enabled'):
        titles = as_exam.get('titles') or {}
        for q in p['questions']:
            fn = q['file']
            if fn not in set_ids:
                set_ids[fn] = c.execute('INSERT INTO exam_sets(folder_id, title, source, created_at) VALUES (?,?,?,?)',
                                        (as_exam.get('folder_id'), (titles.get(fn) or fn).strip(), fn, time.time())).lastrowid
    n = 0
    for i, q in enumerate(p['questions']):
        if i in skip:
            continue
        if q.get('duplicate') and not body.get('keep_duplicates') and not set_ids:
            continue
        e = edits.get(i) or {}
        if 'folder_id' in e:
            q['folder_id'] = e['folder_id'] or None
        if 'level' in e:
            q['level'] = e['level']
        if 'answer' in e:
            q['answer'] = check_answer(q['qtype'], e['answer'], len(q.get('items') or []) or 4)
        if set_ids:
            q['set_id'] = set_ids[q['file']]
            q['set_pos'] = q['no_in_file']
            q['set_part'] = q.get('part_in_file') or 0
        q['plain'] = norm(q['plain'])
        db.insert_question(q)
        n += 1
    c.commit()
    return {'saved': n, 'sets': list(set_ids.values())}

# ================================================================== tạo đề

def _pick(c, qtype, folder, level, n, avoid_days, need_solution, chosen):
    where, args = build_filter(folder, level, qtype, None, avoid_days, need_solution, chosen)
    rows = c.execute('SELECT id, (SELECT COUNT(*) FROM usage u WHERE u.question_id = questions.id) used FROM questions'
                     + where + ' ORDER BY used ASC, RANDOM() LIMIT ?', args + [n]).fetchall()
    return [r['id'] for r in rows]

LVCOLS = ('M1', 'M2', 'M3', 'M4', 'ANY')

@app.post('/api/exam/availability')
def api_availability(body: dict = Body(...)):
    c = db.conn()
    out = []
    for part in body.get('parts', []):
        rows = []
        for row in part.get('rows', []):
            cell = {}
            for lv in LVCOLS:
                where, args = build_filter(row.get('folder'), None if lv == 'ANY' else lv, part['qtype'], None,
                                           body.get('avoid_days', 0), body.get('need_solution'))
                cell[lv] = c.execute('SELECT COUNT(*) FROM questions' + where, args).fetchone()[0]
            rows.append(cell)
        out.append(rows)
    return {'parts': out}

@app.post('/api/exam/generate')
def api_generate(body: dict = Body(...)):
    c = db.conn()
    avoid = int(body.get('avoid_days') or 0)
    need_sol = bool(body.get('need_solution'))
    chosen, parts, short = [], [], []
    if body.get('cart_ids'):
        qs = [q for q in (db.get_question(int(i)) for i in body['cart_ids']) if q]
        for t in ORDER:
            parts.append((t, [q for q in qs if q['qtype'] == t]))
    else:
        for part in body.get('parts', []):
            t, ids = part['qtype'], []
            for row in part.get('rows', []):
                for lv in LVCOLS:
                    n = int(row.get(lv) or 0)
                    if n <= 0:
                        continue
                    got = _pick(c, t, row.get('folder'), None if lv == 'ANY' else lv, n, avoid, need_sol, chosen + ids)
                    if len(got) < n:
                        name = db.folder_path(row.get('folder')) if row.get('folder') else 'Tất cả'
                        short.append(f'{docx_io.TYPE_NAMES[t]} · {name} · {"mức bất kỳ" if lv == "ANY" else lv}: cần {n}, kho còn {len(got)}')
                    ids += got
            chosen += ids
            parts.append((t, [db.get_question(i) for i in ids]))
    if short and not body.get('allow_short'):
        return JSONResponse({'short': short}, status_code=409)
    total = sum(len(qs) for _, qs in parts)
    if total == 0:
        raise HTTPException(400, 'Chưa có câu nào để tạo đề.')
    n_codes = max(1, min(24, int(body.get('n_codes') or 1)))
    start = int(body.get('start_code') or 101)
    codes = [str(start + i) for i in range(n_codes)]
    versions = docx_io.make_versions(parts, codes, bool(body.get('shuffle_q', True)), bool(body.get('shuffle_opt', True)))
    info = {'title': body.get('title') or 'Đề kiểm tra', 'grade': body.get('grade'), 'minutes': body.get('minutes') or 90,
            'center': db.get_setting('center', '')}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for v in versions:
            z.writestr(f'De_{v["code"]}.docx', docx_io.build_exam(media_loader, info, v))
        z.writestr('Dap_an.docx', docx_io.build_answer_key(media_loader, info, versions))
        if body.get('with_solution', True):
            for v in versions:
                z.writestr(f'Loi_giai_{v["code"]}.docx', docx_io.build_exam(media_loader, info, v, solution=True))
    eid = c.execute('INSERT INTO exams(title, created_at, config, n_questions) VALUES (?,?,?,?)',
                    (info['title'], time.time(), json.dumps(body, ensure_ascii=False), total)).lastrowid
    now = time.time()
    c.executemany('INSERT INTO usage(question_id, exam_id, used_at) VALUES (?,?,?)',
                  [(q['id'], eid, now) for _, qs in parts for q in qs])
    c.commit()
    fname = f'{eid:04d}_{safe_name(info["title"])}.zip'
    (EXAM_DIR / fname).write_bytes(buf.getvalue())
    return Response(buf.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition': f'attachment; filename="{fname}"'})

@app.post('/api/export')
def api_export(body: dict = Body(...)):
    ids = [int(x) for x in body.get('ids') or []]
    qs = [q for q in (db.get_question(i) for i in ids) if q]
    if not qs:
        raise HTTPException(400, 'Chưa chọn câu nào')
    parts = [(t, [(q, [0, 1, 2, 3]) for q in qs if q['qtype'] == t]) for t in ORDER]
    info = {'title': body.get('title') or 'Tuyển tập câu hỏi', 'center': db.get_setting('center', ''), 'minutes': ''}
    data = docx_io.build_exam(media_loader, info, {'code': '', 'parts': parts}, solution=bool(body.get('solution', True)))
    return Response(data, media_type=DOCX_MIME, headers={'Content-Disposition': 'attachment; filename="cau_hoi_da_chon.docx"'})

@app.get('/api/exams')
def api_exams():
    rows = db.conn().execute('SELECT id, title, created_at, n_questions FROM exams ORDER BY id DESC LIMIT 50').fetchall()
    return [{'id': r['id'], 'title': r['title'], 'n': r['n_questions'],
             'at': datetime.fromtimestamp(r['created_at']).strftime('%d/%m/%Y %H:%M')} for r in rows]

@app.get('/api/exams/{eid}/zip')
def api_exam_zip(eid: int):
    for f in EXAM_DIR.glob(f'{eid:04d}_*.zip'):
        return FileResponse(f, filename=f.name)
    raise HTTPException(404)

@app.get('/api/settings')
def api_settings():
    return {'center': db.get_setting('center', '')}

@app.put('/api/settings')
def api_put_settings(body: dict = Body(...)):
    if 'center' in body:
        db.set_setting('center', body['center'])
    return {'ok': True}

@app.post('/api/tools/mathtype')
async def api_tool_mathtype(file: UploadFile = File(...)):
    """Chỉ đổi MathType → Equation, trả lại file Word (không nhập vào kho)."""
    data = await file.read()
    try:
        out, st = mathtype_convert.convert_docx(data)
    except Exception as e:
        raise HTTPException(400, f'Không đọc được file: {e}')
    stem = re.sub(r'\.docx$', '', file.filename or 'file', flags=re.I)
    from urllib.parse import quote
    return Response(out, media_type=DOCX_MIME, headers={
        'Content-Disposition': f'attachment; filename="{safe_name(stem)}_Equation.docx"; filename*=UTF-8\'\'{quote(stem + " (Equation).docx")}',
        'X-Converted': str(st['converted']), 'X-Failed': str(st['failed'])})

@app.get('/api/backup')
def api_backup():
    """Sao lưu toàn bộ kho ra một file .db (an toàn kể cả khi đang dùng)."""
    import tempfile, os
    fd, tmp = tempfile.mkstemp(suffix='.db'); os.close(fd)
    dst = sqlite3.connect(tmp)
    db.conn().backup(dst)
    dst.close()
    data = Path(tmp).read_bytes(); os.remove(tmp)
    name = 'SaoLuu_KhoDeToan_' + datetime.now().strftime('%Y%m%d_%H%M') + '.db'
    return Response(data, media_type='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="{name}"'})

@app.get('/api/info')
def api_info():
    c = db.conn()
    return {'data_dir': str(db.DATA_DIR), 'questions': c.execute('SELECT COUNT(*) FROM questions').fetchone()[0],
            'size_mb': round(sum(f.stat().st_size for f in db.DATA_DIR.glob('kho.db*')) / 1048576, 1)}

@app.get('/mau-nhap-cau-hoi.docx')
def sample_file():
    return FileResponse(STATIC / 'mau-nhap-cau-hoi.docx', filename='Mau_nhap_cau_hoi.docx')

app.mount('/', StaticFiles(directory=STATIC, html=True), name='static')
