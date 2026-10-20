"""Đọc file Word theo mẫu chuẩn của kho, hiển thị xem trước, và ghép đề thi ra Word.

Nguyên tắc: không bao giờ gõ lại nội dung. Mỗi câu được lưu dưới dạng các đoạn XML gốc
(chữ, công thức Equation/MathType, hình), khi xuất đề chỉ ghép các khối đó lại."""
import copy, hashlib, html, io, posixpath, random, re, zipfile
from lxml import etree
from . import omml

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
PR = 'http://schemas.openxmlformats.org/package/2006/relationships'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
V = 'urn:schemas-microsoft-com:vml'
NS = {'w': W, 'r': R, 'm': M, 'a': A, 'wp': WP, 'v': V}
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'

def w(tag):
    return '{%s}%s' % (W, tag)

def ln(e):
    return etree.QName(e).localname if isinstance(e.tag, str) else ''

def text_of(el):
    return ''.join(el.xpath('.//w:t/text()', namespaces=NS))

def plain_of(el):
    """Chữ + công thức dạng thô, để tìm kiếm và đoán độ dài."""
    out = []
    for e in el.iter():
        if e.tag == w('t'):
            out.append(e.text or '')
        elif e.tag == '{%s}t' % M:
            out.append(e.text or '')
    return ''.join(out)

def tostr(el):
    return etree.tostring(el, encoding='unicode')

def fromstr(s):
    return etree.fromstring(s)

TYPES = ('TN', 'ĐS', 'TLN', 'TL')
TYPE_NAMES = {'TN': 'Trắc nghiệm ABCD', 'ĐS': 'Đúng/Sai', 'TLN': 'Trả lời ngắn', 'TL': 'Tự luận'}
LABEL_RE = re.compile(r'^\s*\[\s*([0-9A-Za-z.]*)\s*\]\s*\[\s*(M[1-4])?\s*\]\s*\[\s*(TN|ĐS|DS|TLN|TL)?\s*\]')
CAU_RE = re.compile(r'^\s*Câu\s+(\d+)\s*[.:]?\s*', re.I)
LOIGIAI_RE = re.compile(r'^\s*(Lời giải|Hướng dẫn giải|Giải)\s*[.:]?\s*$', re.I)
DAPAN_RE = re.compile(r'^\s*Đáp án\s*[:.]\s*(.+?)\s*$', re.I)
SKIP_RE = re.compile(r'^\s*(-+\s*HẾT\s*-+|PHẦN\s+[IVX]+\b.*)\s*$', re.I)
OPT_RE = re.compile(r'^\s*([A-D])\s*\.\s*(.*)$', re.S)
ITEM_RE = re.compile(r'^\s*([a-d])\)\s*(.*)$', re.S)
DROP_TAGS = {'footnoteReference', 'endnoteReference', 'commentReference', 'commentRangeStart', 'commentRangeEnd',
             'proofErr', 'bookmarkStart', 'bookmarkEnd'}

# ---------------------------------------------------------------- đọc file

class ImportResult:
    def __init__(self):
        self.questions = []   # list[dict]
        self.media = {}       # hash -> (bytes, ext)
        self.warnings = []    # cảnh báo chung của file

def _run_text(r):
    return ''.join(t.text or '' for t in r.findall('w:t', NS))

def _is_underlined(r):
    u = r.find('w:rPr/w:u', NS)
    return u is not None and u.get(w('val'), 'single') not in ('none', '0')

def _is_red(r):
    c = r.find('w:rPr/w:color', NS)
    if c is None:
        return False
    v = (c.get(w('val')) or '').upper()
    return v in ('FF0000', 'C00000', 'E00000', 'FF0000FF', 'RED')

def _clean(el):
    for e in list(el.iter()):
        if ln(e) in DROP_TAGS and e.getparent() is not None:
            e.getparent().remove(e)
    for e in el.iter(w('numPr')):
        e.getparent().remove(e)
    return el

def _has_content(el):
    return bool(plain_of(el).strip()) or bool(el.xpath('.//w:drawing|.//w:pict|.//w:object|.//m:oMath', namespaces=NS))

def _strip_prefix(p, regex):
    """Bỏ phần chữ khớp regex ở đầu đoạn (vd 'Câu 3.'). Trả về match hoặc None."""
    for r in p.findall('w:r', NS):
        t = _run_text(r)
        if not t:
            if r.find('w:tab', NS) is not None:
                continue
            continue
        m = regex.match(t)
        if not m:
            return None
        rest = t[m.end():]
        if rest:
            ts = r.findall('w:t', NS)
            ts[0].text = rest
            ts[0].set(XML_SPACE, 'preserve')
            for extra in ts[1:]:
                r.remove(extra)
        else:
            p.remove(r)
        return m
    return None

def _content_nodes(p):
    return [c for c in p if ln(c) not in ('pPr',)]

def _new_run_like(r, text):
    nr = etree.Element(w('r'))
    rpr = r.find('w:rPr', NS)
    if rpr is not None:
        rpr = copy.deepcopy(rpr)
        for u in rpr.findall('w:u', NS):
            rpr.remove(u)
        nr.append(rpr)
    t = etree.SubElement(nr, w('t'))
    t.text = text
    t.set(XML_SPACE, 'preserve')
    return nr

MARK_RE = re.compile(r'(?:(?<=^)|(?<=\s))([A-D])\s*\.(?=\s|$)')

def _presplit(p):
    """Tách run chứa nhiều phương án ('A. 2   B. 3') thành nhiều run; gộp 'A' + '.' bị tách."""
    # tách run có nhiều <w:t>/<w:tab> thành từng run riêng để nhận ra 'C.' đứng sau dấu tab
    for r in p.findall('w:r', NS):
        kids = [c for c in r if ln(c) != 'rPr']
        if len(kids) > 1 and all(ln(c) in ('t', 'tab') for c in kids):
            parent, pos = r.getparent(), r.getparent().index(r)
            for k, c in enumerate(kids):
                nr = etree.Element(w('r'))
                if r.find('w:rPr', NS) is not None:
                    nr.append(copy.deepcopy(r.find('w:rPr', NS)))
                nr.append(c)
                parent.insert(pos + k, nr)
            parent.remove(r)
    runs = p.findall('w:r', NS)
    for i, r in enumerate(runs):
        t = _run_text(r)
        if re.fullmatch(r'\s*[A-D]\s*', t) and i + 1 < len(runs):
            nt = runs[i + 1].findall('w:t', NS)
            if nt and (nt[0].text or '').startswith('.'):
                r.findall('w:t', NS)[-1].text = t.strip() + '.'
                nt[0].text = nt[0].text[1:]
                nt[0].set(XML_SPACE, 'preserve')
    for r in p.findall('w:r', NS):
        t = _run_text(r)
        ms = list(MARK_RE.finditer(t))
        if not ms or (len(ms) == 1 and ms[0].start() == len(t) - len(t.lstrip()) and t[ms[0].end():].strip() == ''):
            continue
        cuts = sorted({0} | {m.start() for m in ms} | {m.end() for m in ms} | {len(t)})
        pieces = [t[a:b] for a, b in zip(cuts, cuts[1:]) if t[a:b]]
        if len(pieces) < 2:
            continue
        parent, pos = r.getparent(), r.getparent().index(r)
        for k, piece in enumerate(pieces):
            nr = copy.deepcopy(r)
            for ch in list(nr):
                if ln(ch) != 'rPr':
                    nr.remove(ch)
            tt = etree.SubElement(nr, w('t')); tt.text = piece; tt.set(XML_SPACE, 'preserve')
            if not re.fullmatch(r'\s*[A-D]\s*\.\s*', piece):
                u = nr.find('w:rPr/w:u', NS)
                if u is not None:
                    u.getparent().remove(u)
            parent.insert(pos + k, nr)
        parent.remove(r)

def _split_options(paras):
    """Tách các đoạn phương án thành 4 nhóm node. Trả về (opts, correct_letter, ok)."""
    opts, cur, correct = {}, None, None
    for p in paras:
        _presplit(p)
    for p in paras:
        for node in _content_nodes(p):
            if ln(node) == 'r':
                t = _run_text(node)
                if not t.strip():
                    if node.find('w:tab', NS) is not None or not t:
                        if cur is not None and t:  # khoảng trắng trong phương án
                            opts[cur].append(node)
                        continue
                m = OPT_RE.match(t)
                if m and (cur is None or m.group(1) > cur):
                    cur = m.group(1)
                    opts[cur] = []
                    if _is_underlined(node) or _is_red(node):
                        correct = cur
                    rest = m.group(2)
                    if rest.strip():
                        opts[cur].append(_new_run_like(node, rest))
                    continue
            if cur is not None:
                if ln(node) == 'r':
                    for tb in node.findall('w:tab', NS) + node.findall('w:br', NS):
                        node.remove(tb)
                    if not _run_text(node) and not node.xpath('.//w:drawing|.//w:object|.//w:pict', namespaces=NS):
                        continue
                opts[cur].append(node)
    for k in opts:  # bỏ khoảng trắng đầu phương án
        if opts[k] and ln(opts[k][0]) == 'r':
            ts = opts[k][0].findall('w:t', NS)
            if ts and ts[0].text:
                ts[0].text = ts[0].text.lstrip()
    for k in opts:  # bỏ khoảng trắng cuối mỗi phương án
        while opts[k] and ln(opts[k][-1]) == 'r' and not _run_text(opts[k][-1]).strip() \
                and not opts[k][-1].xpath('.//w:drawing|.//w:object', namespaces=NS):
            opts[k].pop()
        if opts[k] and ln(opts[k][-1]) == 'r':
            ts = opts[k][-1].findall('w:t', NS)
            if ts and ts[-1].text:
                ts[-1].text = ts[-1].text.rstrip()
    ok = sorted(opts) == ['A', 'B', 'C', 'D']
    # bỏ dấu cách thừa ở đầu/cuối
    return [opts.get(k, []) for k in 'ABCD'], correct, ok

def classify_blocks(blocks):
    """Đoán dạng câu khi không có nhãn và không có tiêu đề PHẦN."""
    txts = [text_of(b) for b in blocks]
    if any(DAPAN_RE.match(t) for t in txts):
        return 'TLN'
    if any(re.match(r'^\s*A\s*\.', t) for t in txts) and any(re.search(r'[CD]\s*\.', t) for t in txts):
        return 'TN'
    items = [t for t in txts if ITEM_RE.match(t)]
    if len(items) == 4 and any(ITEM_RE.match(t).group(1) == 'd' for t in items):
        return 'ĐS'
    return 'TL'

def _norm(s):
    import unicodedata
    s = (s or '').lower().replace('đ', 'd')
    return ''.join(ch for ch in unicodedata.normalize('NFD', s) if unicodedata.category(ch) != 'Mn')

PART_RE = re.compile(r'^\s*PHẦN\s+(IV|III|II|I|[1-4])\b\s*[.:\-–]?\s*(.*)$', re.I | re.S)
ANS_SEC_RE = re.compile(r'^\s*(BẢNG\s+)?ĐÁP\s+ÁN\b', re.I)
SOL_SEC_RE = re.compile(r'^\s*(LỜI\s+GIẢI|HƯỚNG\s+DẪN\s+(GIẢI|CHẤM)|ĐÁP\s+ÁN\s+(VÀ|&)\s+(LỜI\s+GIẢI|HƯỚNG\s+DẪN))', re.I)
CHON_ANS_RE = re.compile(r'(?:Chọn|Đáp án)\s*(?:đáp án|phương án)?\s*[:.]?\s*([A-D])\b')
DS_SOL_RE = re.compile(r'^\s*([a-d])\).*?\b(Đúng|Sai)\s*[.!]?\s*$', re.S)

def part_type(text):
    t = _norm(text)
    if 'dung sai' in t or 'dung/sai' in t or 'dung - sai' in t or 'dung hoac sai' in t:
        return 'ĐS'
    if 'tra loi ngan' in t:
        return 'TLN'
    if 'tu luan' in t:
        return 'TL'
    if 'trac nghiem' in t or 'lua chon' in t or 'phuong an' in t:
        return 'TN'
    return None

def _is_heading(t, regex):
    s = t.strip()
    if not s or len(s) > 90 or not regex.match(s):
        return False
    letters = [c for c in s if c.isalpha()]
    upper = sum(1 for c in letters if c.isupper())
    return upper >= 0.6 * max(1, len(letters))

def _cells(tbl):
    return [[' '.join(text_of(tc).split()) for tc in tr.findall('w:tc', NS)] for tr in tbl.findall('w:tr', NS)]

def _parse_key_table(rows):
    """Trả về list[(số câu, giá trị, kiểu)] với kiểu 'TN' | 'ĐS' | 'TLN'."""
    out = []
    flat = ' '.join(' '.join(r) for r in rows)
    # Đúng/sai dạng 'a) Đ' trong ô, cột là câu
    if re.search(r'\b[a-d]\)\s*[ĐSđs]\b', flat):
        heads = rows[0]
        nums = [int(m.group()) if (m := re.search(r'\d+', h)) else None for h in heads]
        for ci, n in enumerate(nums):
            if n is None:
                continue
            val = {}
            for r in rows[1:]:
                if ci < len(r):
                    m = re.match(r'^\s*([a-d])\)\s*([ĐSđs])', r[ci])
                    if m:
                        val[m.group(1)] = 'Đ' if m.group(2) in 'Đđ' else 'S'
            if val:
                out.append((n, ''.join(val.get(l, '?') for l in 'abcd'), 'ĐS'))
        return out
    # Đúng/sai dạng bảng Câu | a | b | c | d
    if rows and [_norm(c) for c in rows[0][1:5]] in (['a', 'b', 'c', 'd'], ['a)', 'b)', 'c)', 'd)']):
        for r in rows[1:]:
            m = re.search(r'\d+', r[0]) if r else None
            if m and len(r) >= 5:
                out.append((int(m.group()), ''.join('Đ' if x.strip()[:1] in 'Đđ' else 'S' for x in r[1:5]), 'ĐS'))
        return out
    # Bảng ngang: hàng 'Câu' + hàng đáp án
    i = 0
    while i < len(rows) - 1:
        r, nx = rows[i], rows[i + 1]
        if r and _norm(r[0]).startswith('cau') and len(nx) == len(r):
            for h, v in zip(r[1:], nx[1:]):
                m = re.search(r'\d+', h)
                if m and v.strip():
                    v = v.strip()
                    out.append((int(m.group()), v, 'TN' if re.fullmatch(r'[A-D]', v) else 'TLN'))
            i += 2
            continue
        i += 1
    if out:
        return out
    # Bảng dọc: các cặp (số câu, đáp án)
    for r in rows:
        for a, b in zip(r[::2], r[1::2]):
            m = re.fullmatch(r'\s*(?:Câu\s*)?(\d+)\s*[.:]?\s*', a, re.I)
            if m and b.strip():
                v = b.strip()
                out.append((int(m.group(1)), v, 'TN' if re.fullmatch(r'[A-D]', v) else 'TLN'))
    return out

def parse_docx(data: bytes, source_name=''):
    res = ImportResult()
    z = zipfile.ZipFile(io.BytesIO(data))
    doc = etree.fromstring(z.read('word/document.xml'))
    rels = {}
    try:
        rx = etree.fromstring(z.read('word/_rels/document.xml.rels'))
        for rel in rx:
            rels[rel.get('Id')] = (rel.get('Type'), rel.get('Target'), rel.get('TargetMode'))
    except KeyError:
        pass
    body = doc.find('w:body', NS)
    blocks = [b for b in body if ln(b) in ('p', 'tbl')]

    # ---- 1. câu hỏi (dừng ở mục ĐÁP ÁN / LỜI GIẢI cuối file)
    raw, cur, pending, mode = [], None, None, 'stem'
    part_idx, ptype = 0, None
    section_start = len(blocks)
    for bi, b in enumerate(blocks):
        t = text_of(b) if ln(b) == 'p' else ''
        if ln(b) == 'p':
            if raw and not LOIGIAI_RE.match(t) and (_is_heading(t, ANS_SEC_RE) or _is_heading(t, SOL_SEC_RE)):
                section_start = bi
                break
            lm = LABEL_RE.match(t)
            if lm:
                pending, cur = lm, None
                continue
            pm = PART_RE.match(t)
            if pm:
                part_idx += 1
                ptype = part_type(pm.group(2))
                cur = None
                continue
            if CAU_RE.match(t) and (cur is None or mode == 'sol' or cur['stem']):
                cur = {'label': pending, 'stem': [b], 'sol': [], 'part': part_idx, 'ptype': ptype,
                       'num': int(CAU_RE.match(t).group(1))}
                pending, mode = None, 'stem'
                raw.append(cur)
                continue
            if cur is not None and LOIGIAI_RE.match(t):
                mode = 'sol'
                continue
            if SKIP_RE.match(t):
                continue
        if cur is None:
            continue
        cur['stem' if mode == 'stem' else 'sol'].append(b)

    # ---- 2. bảng đáp án và lời giải ở cuối file
    keys, sols = {}, {}
    sec, kpart, spart, scur = None, 0, 0, None
    key_seq = []
    for b in blocks[section_start:]:
        t = text_of(b) if ln(b) == 'p' else ''
        if ln(b) == 'p':
            if _is_heading(t, SOL_SEC_RE) and not LOIGIAI_RE.match(t) or (sec != 'sol' and LOIGIAI_RE.match(t)):
                sec, spart, scur = 'sol', 0, None
                continue
            if _is_heading(t, ANS_SEC_RE):
                sec, kpart = 'key', 0
                continue
            pm = PART_RE.match(t)
            if pm and len(t) < 120:
                if sec == 'key':
                    kpart += 1
                else:
                    spart += 1; scur = None
                continue
            if SKIP_RE.match(t):
                continue
        if sec == 'key':
            if ln(b) == 'tbl':
                for n, v, kind in _parse_key_table(_cells(b)):
                    key_seq.append((kpart, n, v, kind))
            elif t.strip():
                for n, v in re.findall(r'\b(\d{1,3})\s*[.:\-–)]?\s*([A-D])\b', t):
                    key_seq.append((kpart, int(n), v, 'TN'))
        elif sec == 'sol':
            m = CAU_RE.match(t) if ln(b) == 'p' else None
            if m:
                scur = (spart, int(m.group(1)))
                sols[scur] = [b]
            elif scur:
                sols[scur].append(b)

    # ghép đáp án vào câu: theo (phần, số câu); nếu bảng không chia phần thì theo kiểu câu
    q_by_part = {(rq['part'], rq['num']): rq for rq in raw}
    parts_of_type = {}
    for rq in raw:
        parts_of_type.setdefault(rq['ptype'], [])
        if rq['part'] not in parts_of_type[rq['ptype']]:
            parts_of_type[rq['ptype']].append(rq['part'])
    has_key_parts = any(kp for kp, *_ in key_seq)
    for kp, n, v, kind in key_seq:
        rq = None
        if has_key_parts:
            rq = q_by_part.get((kp, n))
        else:
            for p in parts_of_type.get(kind, []) or [0]:
                rq = q_by_part.get((p, n))
                if rq:
                    break
        if rq is not None:
            rq['key'] = v
    has_sol_parts = any(sp for sp, _ in sols)
    for (sp, n), bl in sols.items():
        rq = q_by_part.get((sp, n)) if has_sol_parts else next((r for r in raw if r['num'] == n), None)
        if rq is not None and not rq['sol']:
            rq['sol'] = bl
            rq['sol_from_section'] = True

    if not raw:
        res.warnings.append('Không tìm thấy câu nào bắt đầu bằng “Câu …”.')
    for i, rq in enumerate(raw, 1):
        q = _build_question(rq, i, rels, z, res)
        if q:
            q['source'] = source_name
            res.questions.append(q)
    return res

def _sol_text(sol):
    return [text_of(b) for b in sol if ln(b) == 'p']

def _build_question(rq, idx, rels, z, res):
    warn = []
    stem = [_clean(copy.deepcopy(b)) for b in rq['stem']]
    sol = [_clean(copy.deepcopy(b)) for b in rq['sol']]
    if rq.get('sol_from_section') and sol:
        _strip_prefix(sol[0], CAU_RE)
    lab = rq['label']
    code = (lab.group(1) or '').strip() if lab else ''
    level = (lab.group(2) or '') if lab else ''
    qtype = (lab.group(3) or '') if lab else ''
    if qtype == 'DS':
        qtype = 'ĐS'
    if not qtype:
        qtype = rq.get('ptype') or classify_blocks(stem)
    if not code:
        warn.append('Chưa có chuyên đề')
    if not level:
        warn.append('Chưa có mức độ')

    _strip_prefix(stem[0], CAU_RE)
    q = {'code': code, 'level': level, 'qtype': qtype, 'options': None, 'items': None,
         'answer': None, 'no_in_file': idx, 'part_in_file': rq.get('part', 0), 'num_in_file': rq.get('num')}
    key = rq.get('key')

    if qtype == 'TN':
        k = next((i for i, b in enumerate(stem) if ln(b) == 'p' and re.match(r'^\s*A\s*\.', text_of(b))), None)
        if k is None:
            warn.append('Không tìm thấy phương án A, B, C, D')
            q['qtype'] = 'TL'
        else:
            opts, correct, ok = _split_options(stem[k:])
            if not ok:
                warn.append('Không tách đủ 4 phương án')
            if key and re.fullmatch(r'[A-D]', key):
                if correct and correct != key:
                    warn.append(f'Đáp án gạch chân ({correct}) khác bảng đáp án ({key}) — đang lấy theo bảng')
                correct = key
            if not correct:
                for t in reversed(_sol_text(sol)):
                    m = CHON_ANS_RE.findall(t)
                    if m:
                        correct = m[-1]
                        warn.append('Đáp án lấy từ câu “Chọn …” trong lời giải')
                        break
            if not correct:
                warn.append('Chưa có đáp án')
            q['options'] = [[tostr(n) for n in o] for o in opts]
            q['answer'] = correct
            stem = stem[:k]
    elif qtype == 'ĐS':
        k = next((i for i, b in enumerate(stem) if ln(b) == 'p' and ITEM_RE.match(text_of(b))), None)
        if k is None:
            warn.append('Không tìm thấy các ý a), b), c), d)')
        else:
            items, ans = [], {}
            for b in stem[k:]:
                if ln(b) != 'p' or not ITEM_RE.match(text_of(b)):
                    if items:
                        items[-1].append(b)
                    continue
                first = next((r for r in b.findall('w:r', NS) if _run_text(r).strip()), None)
                letter = ITEM_RE.match(text_of(b)).group(1)
                if first is not None and (_is_underlined(first) or _is_red(first)):
                    ans[letter] = 'Đ'
                _strip_prefix(b, re.compile(r'^\s*[a-d]\)\s*'))
                items.append([b])
            if len(items) != 4:
                warn.append(f'Có {len(items)} ý, cần đúng 4 ý a)–d)')
            answer = None
            if key and re.fullmatch(r'[ĐS?]{4}', key):
                answer = key
            elif ans:
                answer = ''.join(ans.get(l, 'S') for l in 'abcd'[:len(items)])
            else:
                sol_ans = {}
                for t in _sol_text(sol):
                    m = DS_SOL_RE.match(t)
                    if m:
                        sol_ans[m.group(1)] = 'Đ' if m.group(2) == 'Đúng' else 'S'
                if len(sol_ans) == len(items) and items:
                    answer = ''.join(sol_ans[l] for l in 'abcd'[:len(items)])
                    warn.append('Đáp án Đúng/Sai lấy từ lời giải')
            if not answer or '?' in answer:
                warn.append('Chưa có đáp án Đúng/Sai')
            q['items'] = [[tostr(b) for b in it] for it in items]
            q['answer'] = answer
            stem = stem[:k]
    elif qtype == 'TLN':
        keep = []
        for b in stem:
            m = DAPAN_RE.match(text_of(b)) if ln(b) == 'p' else None
            if m:
                q['answer'] = m.group(1).strip()
            else:
                keep.append(b)
        stem = keep
        if key and not q['answer']:
            q['answer'] = key
        if not q['answer']:
            for t in _sol_text(sol):
                m = DAPAN_RE.match(t)
                if m:
                    q['answer'] = m.group(1).strip()
        if not q['answer']:
            warn.append('Chưa có đáp án')

    stem = [b for b in stem if _has_content(b)] or stem[:1]
    while sol and not _has_content(sol[-1]):
        sol.pop()
    while sol and not _has_content(sol[0]):
        sol.pop(0)
    q['stem'] = [tostr(b) for b in stem]
    q['solution'] = [tostr(b) for b in sol]
    if not sol:
        warn.append('Không có lời giải')

    # hình ảnh / đối tượng nhúng
    all_xml = ''.join(q['stem'] + q['solution'] + sum(q['options'] or [], []) + sum(q['items'] or [], []))
    qrels = {}
    for rid in set(re.findall(r'r:(?:id|embed|link|pict)="(rId[^"]+)"', all_xml)) | set(re.findall(r'\s(?:o|v):\w*="(rId[^"]+)"', all_xml)):
        if rid not in rels:
            continue
        typ, target, mode = rels[rid]
        if mode == 'External':
            continue
        path = posixpath.normpath(posixpath.join('word', target)) if not target.startswith('/') else target.lstrip('/')
        try:
            blob = z.read(path)
        except KeyError:
            warn.append('Thiếu tệp hình/đối tượng ' + target)
            continue
        h = hashlib.sha1(blob).hexdigest()
        ext = posixpath.splitext(path)[1].lstrip('.').lower() or 'bin'
        res.media[h] = (blob, ext)
        qrels[rid] = {'type': typ, 'hash': h, 'ext': ext}
    q['rels'] = qrels

    plain = ' '.join(plain_of(fromstr(x)) for x in q['stem'])
    if q['options']:
        plain += ' ' + ' '.join(''.join(plain_of(fromstr(x)) for x in o) for o in q['options'])
    if q['items']:
        plain += ' ' + ' '.join(plain_of(fromstr(x)) for it in q['items'] for x in it)
    q['plain'] = ' '.join(plain.split())
    q['fingerprint'] = hashlib.sha1(re.sub(r'\W+', '', q['plain'].lower()).encode()).hexdigest()
    q['warnings'] = warn
    return q

# ---------------------------------------------------------------- xem trước HTML

def _emu_px(v):
    try:
        return max(20, int(int(v) / 9525))
    except (TypeError, ValueError):
        return None

def _html_run(r, rels):
    out = []
    for c in r:
        n = ln(c)
        if n == 't':
            out.append(html.escape(c.text or ''))
        elif n == 'tab':
            out.append('&emsp;')
        elif n in ('br', 'cr'):
            out.append('<br>')
        elif n == 'drawing':
            blip = c.find('.//a:blip', NS)
            ext = c.find('.//wp:extent', NS)
            rid = blip.get('{%s}embed' % R) if blip is not None else None
            info = rels.get(rid)
            if info and info['ext'] in ('png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg', 'webp'):
                wpx = _emu_px(ext.get('cx')) if ext is not None else None
                style = f' style="width:{wpx}px"' if wpx else ''
                out.append(f'<img class="fig" src="/media/{info["hash"]}.{info["ext"]}"{style} alt="Hình">')
            else:
                out.append('<span class="ph">[hình]</span>')
        elif n in ('object', 'pict'):
            out.append('<span class="ph">[công thức MathType]</span>' if c.find('.//{urn:schemas-microsoft-com:office:office}OLEObject') is not None else '<span class="ph">[hình]</span>')
    s = ''.join(out)
    if not s:
        return ''
    rpr = r.find('w:rPr', NS)
    if rpr is not None:
        if rpr.find('w:b', NS) is not None and rpr.find('w:b', NS).get(w('val'), 'true') not in ('0', 'false'):
            s = f'<b>{s}</b>'
        if rpr.find('w:i', NS) is not None and rpr.find('w:i', NS).get(w('val'), 'true') not in ('0', 'false'):
            s = f'<i>{s}</i>'
        if _is_underlined(r):
            s = f'<u>{s}</u>'
        va = rpr.find('w:vertAlign', NS)
        if va is not None:
            s = {'superscript': f'<sup>{s}</sup>', 'subscript': f'<sub>{s}</sub>'}.get(va.get(w('val')), s)
    return s

def html_nodes(nodes, rels):
    out = []
    for c in nodes:
        n = ln(c)
        if n == 'r':
            out.append(_html_run(c, rels))
        elif n == 'oMath':
            out.append('<span class="tex">' + html.escape(omml.to_latex(c)) + '</span>')
        elif n == 'oMathPara':
            for om in c.iter('{%s}oMath' % M):
                out.append('<span class="tex tex-d">' + html.escape(omml.to_latex(om)) + '</span>')
        elif n in ('hyperlink', 'smartTag', 'ins', 'fldSimple', 'sdt', 'sdtContent'):
            out.append(html_nodes(list(c), rels))
    return ''.join(out)

def html_block(el, rels):
    if ln(el) == 'tbl':
        rows = []
        for tr in el.findall('w:tr', NS):
            cells = []
            for tc in tr.findall('w:tc', NS):
                cells.append('<td>' + ''.join(html_block(p, rels) for p in tc if ln(p) in ('p', 'tbl')) + '</td>')
            rows.append('<tr>' + ''.join(cells) + '</tr>')
        return '<table class="wtbl">' + ''.join(rows) + '</table>'
    jc = el.find('w:pPr/w:jc', NS)
    cls = ' class="c"' if jc is not None and jc.get(w('val')) == 'center' else ''
    return f'<p{cls}>' + html_nodes(_content_nodes(el), rels) + '</p>'

def question_parts(q, with_solution=True):
    """Các phần HTML riêng để giao diện tự dựng (chọn đáp án, bảng Đúng/Sai...)."""
    rels = q.get('rels') or {}
    out = {'stem': ''.join(html_block(fromstr(x), rels) for x in q['stem']), 'options': None, 'items': None,
           'solution': None}
    if q.get('options'):
        out['options'] = [html_nodes([fromstr(x) for x in o], rels) for o in q['options']]
    if q.get('items'):
        out['items'] = [''.join(html_nodes(_content_nodes(fromstr(x)), rels) for x in it) for it in q['items']]
    if with_solution and q.get('solution'):
        out['solution'] = ''.join(html_block(fromstr(x), rels) for x in q['solution'])
    return out

def question_html(q, with_solution=True):
    rels = q.get('rels') or {}
    parts = ['<div class="qstem">' + ''.join(html_block(fromstr(x), rels) for x in q['stem']) + '</div>']
    if q['qtype'] == 'TN' and q.get('options'):
        cells = []
        for i, o in enumerate(q['options']):
            L = 'ABCD'[i]
            ok = ' ok' if q.get('answer') == L else ''
            cells.append(f'<div class="opt{ok}"><b>{L}.</b> ' + html_nodes([fromstr(x) for x in o], rels) + '</div>')
        parts.append('<div class="opts">' + ''.join(cells) + '</div>')
    if q['qtype'] == 'ĐS' and q.get('items'):
        rows = []
        ans = q.get('answer') or ''
        for i, it in enumerate(q['items']):
            L = 'abcd'[i]
            mark = ans[i] if i < len(ans) else '?'
            inner = ''.join(html_nodes(_content_nodes(fromstr(x)), rels) for x in it)
            rows.append(f'<div class="item"><b>{L})</b> {inner} <span class="ds ds-{ "d" if mark == "Đ" else "s"}">{"Đúng" if mark == "Đ" else "Sai"}</span></div>')
        parts.append('<div class="items">' + ''.join(rows) + '</div>')
    if q['qtype'] == 'TLN' and q.get('answer'):
        parts.append(f'<p class="tln"><b>Đáp án:</b> {html.escape(q["answer"])}</p>')
    if with_solution and q.get('solution'):
        parts.append('<div class="sol"><div class="solh">Lời giải</div>' + ''.join(html_block(fromstr(x), rels) for x in q['solution']) + '</div>')
    return ''.join(parts)

# ---------------------------------------------------------------- ghép đề ra Word

CT_DEFAULTS = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'bmp': 'image/bmp',
               'wmf': 'image/x-wmf', 'emf': 'image/x-emf', 'tif': 'image/tiff', 'tiff': 'image/tiff', 'svg': 'image/svg+xml',
               'bin': 'application/vnd.openxmlformats-officedocument.oleObject', 'webp': 'image/webp',
               'wdp': 'image/vnd.ms-photo'}

STYLES = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="vi-VN"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:before="20" w:after="20" w:line="264" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>'''

SETTINGS = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="{W}" xmlns:m="{M}"><w:defaultTabStop w:val="720"/><w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat><m:mathPr><m:mathFont m:val="Cambria Math"/><m:dispDef/><m:lMargin m:val="0"/><m:rMargin m:val="0"/><m:defJc m:val="centerGroup"/><m:wrapIndent m:val="1440"/><m:intLim m:val="subSup"/><m:naryLim m:val="undOvr"/></m:mathPr></w:settings>'''

TEXT_WIDTH = 10206  # A4, lề 1.7cm hai bên (twip)

class DocBuilder:
    def __init__(self, media_loader):
        self.body = []
        self.load = media_loader      # hash -> bytes
        self.media = {}               # filename -> bytes
        self.rels = []                # (rId, type, target)
        self._map = {}
        self._n = 0

    # --- tiện ích tạo đoạn
    @staticmethod
    def run(text, b=False, i=False, u=False, sz=None, color=None, caps=False):
        r = etree.Element(w('r'))
        rpr = etree.SubElement(r, w('rPr'))
        if b:
            etree.SubElement(rpr, w('b')); etree.SubElement(rpr, w('bCs'))
        if i:
            etree.SubElement(rpr, w('i')); etree.SubElement(rpr, w('iCs'))
        if caps:
            etree.SubElement(rpr, w('caps'))
        if color:
            etree.SubElement(rpr, w('color')).set(w('val'), color)
        if sz:
            etree.SubElement(rpr, w('sz')).set(w('val'), str(sz)); etree.SubElement(rpr, w('szCs')).set(w('val'), str(sz))
        if u:
            etree.SubElement(rpr, w('u')).set(w('val'), 'single')
        t = etree.SubElement(r, w('t'))
        t.text = text
        t.set(XML_SPACE, 'preserve')
        return r

    @staticmethod
    def tab():
        r = etree.Element(w('r'))
        etree.SubElement(r, w('tab'))
        return r

    @staticmethod
    def para(children=(), align=None, before=None, after=None, tabs=None, indent=None, keep_next=False):
        p = etree.Element(w('p'))
        ppr = etree.SubElement(p, w('pPr'))
        if keep_next:
            etree.SubElement(ppr, w('keepNext'))
        if tabs:
            ts = etree.SubElement(ppr, w('tabs'))
            for pos in tabs:
                t = etree.SubElement(ts, w('tab')); t.set(w('val'), 'left'); t.set(w('pos'), str(pos))
        if before is not None or after is not None:
            sp = etree.SubElement(ppr, w('spacing'))
            if before is not None:
                sp.set(w('before'), str(before))
            if after is not None:
                sp.set(w('after'), str(after))
        if indent:
            etree.SubElement(ppr, w('ind')).set(w('left'), str(indent))
        if align:
            etree.SubElement(ppr, w('jc')).set(w('val'), align)
        for c in children:
            p.append(c)
        return p

    def add(self, el):
        self.body.append(el)
        return el

    def text_par(self, text, **kw):
        style = {k: kw.pop(k) for k in ('b', 'i', 'u', 'sz', 'color', 'caps') if k in kw}
        return self.add(self.para([self.run(text, **style)], **kw))

    # --- nhập khối XML của một câu, đổi lại rId
    def imp(self, xml, q):
        el = fromstr(xml) if isinstance(xml, str) else copy.deepcopy(xml)
        qrels = q.get('rels') or {}
        if qrels:
            for e in el.iter():
                for k, v in list(e.attrib.items()):
                    if v in qrels and (k.startswith('{%s}' % R) or k.startswith('{urn:schemas-microsoft-com')):
                        e.set(k, self._rid(q['id'], v, qrels[v]))
        return el

    def _rid(self, qid, old, info):
        key = (qid, old)
        if key not in self._map:
            self._n += 1
            rid = f'rIdQ{self._n}'
            fname = f'media/q_{info["hash"][:16]}.{info["ext"]}'
            if fname not in self.media:
                self.media[fname] = self.load(info['hash'])
            self.rels.append((rid, info['type'], fname))
            self._map[key] = rid
        return self._map[key]

    def table(self, rows, widths, header_rows=1, borders=True, center=True, bold_first_col=False):
        tbl = etree.Element(w('tbl'))
        tp = etree.SubElement(tbl, w('tblPr'))
        etree.SubElement(tp, w('tblW')).attrib.update({w('w'): str(sum(widths)), w('type'): 'dxa'})
        if center:
            etree.SubElement(tp, w('jc')).set(w('val'), 'center')
        bd = etree.SubElement(tp, w('tblBorders'))
        for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
            b = etree.SubElement(bd, w(side))
            b.attrib.update({w('val'): 'single' if borders else 'nil', w('sz'): '4', w('space'): '0', w('color'): '000000'})
        etree.SubElement(tp, w('tblLayout')).set(w('type'), 'fixed')
        grid = etree.SubElement(tbl, w('tblGrid'))
        for wd in widths:
            etree.SubElement(grid, w('gridCol')).set(w('w'), str(wd))
        for ri, row in enumerate(rows):
            tr = etree.SubElement(tbl, w('tr'))
            for ci, cell in enumerate(row):
                tc = etree.SubElement(tr, w('tc'))
                tcp = etree.SubElement(tc, w('tcPr'))
                etree.SubElement(tcp, w('tcW')).attrib.update({w('w'): str(widths[ci]), w('type'): 'dxa'})
                etree.SubElement(tcp, w('vAlign')).set(w('val'), 'center')
                if isinstance(cell, list):
                    for p in cell:
                        tc.append(p)
                else:
                    bold = ri < header_rows or (bold_first_col and ci == 0)
                    tc.append(self.para([self.run(str(cell), b=bold)], align='center', before=30, after=30))
        return self.add(tbl)

    def save(self):
        doc = etree.Element(w('document'), nsmap={'w': W, 'r': R, 'm': M, 'wp': WP, 'a': A, 'v': V,
                                                   'o': 'urn:schemas-microsoft-com:office:office',
                                                   'w10': 'urn:schemas-microsoft-com:office:word',
                                                   'wps': 'http://schemas.microsoft.com/office/word/2010/wordprocessingShape',
                                                   'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
                                                   'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
                                                   'w14': 'http://schemas.microsoft.com/office/word/2010/wordml'})
        body = etree.SubElement(doc, w('body'))
        for el in self.body:
            body.append(el)
        sp = etree.SubElement(body, w('sectPr'))
        etree.SubElement(sp, w('pgSz')).attrib.update({w('w'): '11906', w('h'): '16838'})
        etree.SubElement(sp, w('pgMar')).attrib.update({w('top'): '851', w('right'): '850', w('bottom'): '851', w('left'): '850',
                                                        w('header'): '425', w('footer'): '425', w('gutter'): '0'})
        exts = {posixpath.splitext(f)[1].lstrip('.') for f in self.media}
        ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
              '<Default Extension="xml" ContentType="application/xml"/>']
        for e in sorted(exts):
            ct.append(f'<Default Extension="{e}" ContentType="{CT_DEFAULTS.get(e, "application/octet-stream")}"/>')
        ct += ['<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
               '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
               '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>',
               '</Types>']
        rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', f'<Relationships xmlns="{PR}">',
                '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
                '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>']
        for rid, typ, target in self.rels:
            rels.append(f'<Relationship Id="{rid}" Type="{html.escape(typ)}" Target="{target}"/>')
        rels.append('</Relationships>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('[Content_Types].xml', '\n'.join(ct))
            z.writestr('_rels/.rels', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PR}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
            z.writestr('word/document.xml', etree.tostring(doc, xml_declaration=True, encoding='UTF-8', standalone=True))
            z.writestr('word/styles.xml', STYLES)
            z.writestr('word/settings.xml', SETTINGS)
            z.writestr('word/_rels/document.xml.rels', '\n'.join(rels))
            for fname, blob in self.media.items():
                z.writestr('word/' + fname, blob)
        return buf.getvalue()

# --- đặt câu hỏi vào tài liệu

def _opt_len(nodes_xml):
    n = 0
    for x in nodes_xml:
        e = fromstr(x)
        if e.xpath('.//w:drawing|.//w:pict|.//w:object', namespaces=NS):
            return 999
        n += len(plain_of(e))
        n += 3 * len(e.xpath('.//m:f|.//m:rad|.//m:nary|.//m:d[.//m:eqArr]', namespaces=NS))
        if e.xpath('.//m:eqArr|.//m:m', namespaces=NS):
            n += 4
    return n

def _first_par_with_number(b, stem_els, label):
    """Gắn 'Câu k.' vào đầu đoạn đầu tiên của câu."""
    if stem_els and ln(stem_els[0]) == 'p':
        p = stem_els[0]
        ppr = p.find('w:pPr', NS)
        pos = 1 if ppr is not None else 0
        p.insert(pos, b.run(label + ' ', b=True, color='000000'))
        sp = ppr.find('w:spacing', NS) if ppr is not None else None
        if ppr is not None and sp is None:
            pass
        return stem_els
    return [b.para([b.run(label, b=True)])] + stem_els

CHON_RE = re.compile(r'(Chọn\s+(?:đáp án\s+|phương án\s+)?)([A-D])\b')

def place_question(b, q, label, perm=None, show_key=False, solution=False):
    """perm: thứ tự phương án mới, vd [2,0,3,1] nghĩa là phương án A mới = phương án C cũ."""
    stem = [b.imp(x, q) for x in q['stem']]
    for el in _first_par_with_number(b, stem, label):
        b.add(el)
    if q['qtype'] == 'TN' and q.get('options'):
        perm = perm or [0, 1, 2, 3]
        opts = [q['options'][i] for i in perm]
        new_correct = None
        if q.get('answer') in 'ABCD' and q.get('answer'):
            new_correct = 'ABCD'[perm.index('ABCD'.index(q['answer']))]
        mx = max(_opt_len(o) for o in opts)
        per_line = 4 if mx <= 14 else (2 if mx <= 38 else 1)
        step = TEXT_WIDTH // per_line
        tabs = [283 + i * step for i in range(per_line)]
        for start in range(0, 4, per_line):
            kids = []
            for j in range(start, start + per_line):
                L = 'ABCD'[j]
                kids.append(b.tab())
                kids.append(b.run(L + '. ', b=True, u=(show_key and L == new_correct), color='C00000' if (show_key and L == new_correct) else None))
                for x in opts[j]:
                    kids.append(b.imp(x, q))
            b.add(b.para(kids, tabs=tabs, align='left'))
    elif q['qtype'] == 'ĐS' and q.get('items'):
        ans = q.get('answer') or ''
        for i, it in enumerate(q['items']):
            L = 'abcd'[i]
            for k, x in enumerate(it):
                el = b.imp(x, q)
                if k == 0:
                    ppr = el.find('w:pPr', NS)
                    if ppr is None:
                        ppr = etree.Element(w('pPr')); el.insert(0, ppr)
                    for old in ppr.findall('w:ind', NS):
                        ppr.remove(old)
                    ind = etree.Element(w('ind')); ind.set(w('left'), '283')
                    after = {'contextualSpacing', 'mirrorIndents', 'suppressOverlap', 'jc', 'textDirection', 'textAlignment',
                             'textboxTightWrap', 'outlineLvl', 'divId', 'cnfStyle', 'rPr', 'sectPr', 'pPrChange'}
                    pos = next((i for i, ch in enumerate(ppr) if ln(ch) in after), len(ppr))
                    ppr.insert(pos, ind)
                    el.insert(1, b.run(L + ') ', b=True, u=(show_key and i < len(ans) and ans[i] == 'Đ')))
                b.add(el)
    if solution:
        if q['qtype'] == 'TLN' and q.get('answer'):
            b.add(b.para([b.run('Đáp án: ', b=True), b.run(q['answer'])]))
        if q.get('solution'):
            b.add(b.para([b.run('Lời giải', b=True, i=True)], align='center', before=60))
            mapping = None
            if q['qtype'] == 'TN' and perm:
                mapping = {'ABCD'[old]: 'ABCD'[new] for new, old in enumerate(perm)}
            for x in q['solution']:
                el = b.imp(x, q)
                if mapping:
                    for t in el.iter(w('t')):
                        if t.text and 'Chọn' in t.text:
                            t.text = CHON_RE.sub(lambda m: m.group(1) + mapping.get(m.group(2), m.group(2)), t.text)
                b.add(el)

PART_HEAD = {
    'TN': 'Câu hỏi trắc nghiệm nhiều lựa chọn. Thí sinh trả lời từ Câu 1 đến Câu {n}. Mỗi câu hỏi thí sinh chỉ chọn một phương án.',
    'ĐS': 'Trắc nghiệm đúng sai. Thí sinh trả lời từ Câu 1 đến Câu {n}. Trong mỗi ý a), b), c), d) ở mỗi câu, thí sinh chọn đúng hoặc sai.',
    'TLN': 'Trắc nghiệm trả lời ngắn. Thí sinh trả lời từ Câu 1 đến Câu {n}.',
    'TL': 'Tự luận. Thí sinh làm từ Câu 1 đến Câu {n}.',
}
ROMAN = ['I', 'II', 'III', 'IV']

def exam_header(b, info, code, kind='ĐỀ'):
    left = [b.para([b.run(info.get('center') or '[TÊN TRUNG TÂM]', b=True, caps=True)], align='center', after=0),
            b.para([b.run('–––––––––––')], align='center', after=0)]
    if kind != 'ĐỀ':
        left.append(b.para([b.run(kind, b=True, color='C00000')], align='center'))
    right = [b.para([b.run(info.get('title') or 'ĐỀ KIỂM TRA', b=True, caps=True)], align='center', after=0),
             b.para([b.run('MÔN: TOÁN' + (f' – LỚP {info["grade"]}' if info.get('grade') else ''), b=True)], align='center', after=0)]
    if info.get('minutes'):
        right += [b.para([b.run(f'Thời gian làm bài: {info["minutes"]} phút', i=True)], align='center', after=0),
                  b.para([b.run('(không kể thời gian phát đề)', i=True)], align='center', after=0)]
    b.table([[left, right]], [4300, 5906], header_rows=0, borders=False)
    line = [b.run('Họ và tên: ................................................................. Lớp: ............')]
    if code:
        line += [b.tab(), b.run(f'Mã đề {code}', b=True)]
    b.add(b.para(line, tabs=[8300], before=200, after=120))

def build_exam(media_loader, info, version, solution=False):
    """version: {'code': '101', 'parts': [(qtype, [(q, perm), ...]), ...]}"""
    b = DocBuilder(media_loader)
    exam_header(b, info, version['code'], kind='LỜI GIẢI CHI TIẾT' if solution else 'ĐỀ')
    pi = 0
    for qtype, items in version['parts']:
        if not items:
            continue
        b.add(b.para([b.run(f'PHẦN {ROMAN[pi]}. ', b=True), b.run(PART_HEAD[qtype].format(n=len(items)))],
                     before=160, after=60, keep_next=True))
        pi += 1
        for k, (q, perm) in enumerate(items, 1):
            place_question(b, q, f'Câu {k}.', perm=perm, show_key=solution, solution=solution)
    b.add(b.para([b.run('------ HẾT ------', b=True)], align='center', before=240))
    return b.save()

def build_answer_key(media_loader, info, versions):
    b = DocBuilder(media_loader)
    b.text_par((info.get('title') or 'ĐỀ KIỂM TRA').upper(), b=True, align='center', after=0)
    b.text_par('ĐÁP ÁN', b=True, color='C00000', align='center', after=200)
    for v in versions:
        b.text_par(f'MÃ ĐỀ {v["code"]}', b=True, before=240, after=80)
        pi = 0
        for qtype, items in v['parts']:
            if not items:
                continue
            b.text_par(f'Phần {ROMAN[pi]}', b=True, i=True, before=80, after=40)
            pi += 1
            if qtype in ('TN', 'TLN'):
                keys = []
                for q, perm in items:
                    if qtype == 'TN':
                        a = q.get('answer') or '?'
                        if a in 'ABCD' and a != '?' and perm:
                            a = 'ABCD'[perm.index('ABCD'.index(a))]
                    else:
                        a = q.get('answer') or '?'
                    keys.append(a)
                per = 12 if qtype == 'TN' else 6
                for s in range(0, len(keys), per):
                    chunk = keys[s:s + per]
                    widths = [1100] + [(TEXT_WIDTH - 1100) // per] * len(chunk)
                    b.table([['Câu'] + [str(s + i + 1) for i in range(len(chunk))], ['Chọn'] + chunk], widths,
                            bold_first_col=True)
                    b.add(b.para([], after=40))
            elif qtype == 'ĐS':
                rows = [['Câu', 'a)', 'b)', 'c)', 'd)']]
                for k, (q, _) in enumerate(items, 1):
                    a = (q.get('answer') or '????').ljust(4, '?')
                    rows.append([str(k)] + list(a[:4]))
                b.table(rows, [1100, 1300, 1300, 1300, 1300], bold_first_col=True)
                b.add(b.para([], after=40))
            else:
                b.text_par(f'{len(items)} câu tự luận — xem file lời giải chi tiết.', i=True)
    return b.save()

def make_versions(parts, codes, shuffle_q=True, shuffle_opt=True, seed=None):
    """parts: [(qtype, [q,...])] -> list of versions."""
    rnd = random.Random(seed)
    versions = []
    for vi, code in enumerate(codes):
        vparts = []
        for qtype, qs in parts:
            order = list(qs)
            if shuffle_q:
                rnd.shuffle(order)
            items = []
            for q in order:
                perm = [0, 1, 2, 3]
                if qtype == 'TN' and shuffle_opt:
                    rnd.shuffle(perm)
                items.append((q, perm))
            vparts.append((qtype, items))
        versions.append({'code': code, 'parts': vparts})
    return versions
