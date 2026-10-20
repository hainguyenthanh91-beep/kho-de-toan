"""Đọc công thức MathType (MTEF v5, trong luồng "Equation Native" của đối tượng OLE) và đổi sang LaTeX.

Dùng để chuyển file Word có MathType sang Equation (OMML) mà không cần Word/MathType.
"""
import struct

class MTEFError(Exception):
    pass

# --- record types
END, LINE, CHAR, TMPL, PILE, MATRIX, EMBELL, RULER, FONT_STYLE_DEF, SIZE = range(10)
FULL, SUB, SUB2, SYM, SUBSYM, COLOR, COLOR_DEF, FONT_DEF, EQN_PREFS, ENCODING_DEF = range(10, 20)

O_NUDGE = 0x08
O_CHAR_EMBELL = 0x01
O_CHAR_FUNC_START = 0x02
O_CHAR_ENC_CHAR_8 = 0x04
O_CHAR_ENC_CHAR_16 = 0x10
O_CHAR_ENC_NO_MTCODE = 0x20
O_LINE_NULL = 0x01
O_LP_RULER = 0x02
O_LINE_LSPACE = 0x04

# typefaces
FN_TEXT, FN_FUNCTION, FN_VARIABLE, FN_LCGREEK, FN_UCGREEK, FN_SYMBOL, FN_VECTOR, FN_NUMBER = 1, 2, 3, 4, 5, 6, 7, 8
FN_MTEXTRA = 11

class Node:
    __slots__ = ('kind', 'opts', 'items', 'ch', 'tf', 'emb', 'sel', 'var', 'halign', 'rows', 'cols', 'null')

    def __init__(self, kind):
        self.kind = kind
        self.items = []
        self.emb = []
        self.null = False

class Reader:
    def __init__(self, data):
        self.d = data
        self.i = 0

    def byte(self):
        if self.i >= len(self.d):
            raise MTEFError('hết dữ liệu')
        b = self.d[self.i]
        self.i += 1
        return b

    def u16(self):
        v = struct.unpack_from('<H', self.d, self.i)[0]
        self.i += 2
        return v

    def cstr(self):
        j = self.d.index(b'\0', self.i)
        s = self.d[self.i:j]
        self.i = j + 1
        return s

    def nudge(self, opts):
        if opts & O_NUDGE:
            dx, dy = self.byte(), self.byte()
            if dx == 128 and dy == 128:
                self.i += 4

    def dims(self):
        """Mảng kích thước mã hoá theo nibble (trong EQN_PREFS)."""
        n = self.byte()
        half, cur = False, 0
        def nib():
            nonlocal half, cur
            if not half:
                cur = self.byte()
                half = True
                return cur >> 4
            half = False
            return cur & 0x0F
        for _ in range(n):
            nib()  # đơn vị
            while nib() != 0x0F:
                pass
        # phần dư của byte cuối bị bỏ

def parse_records(r, until_end=True):
    """Đọc danh sách đối tượng cho tới END. Trả về list Node."""
    out = []
    while r.i < len(r.d):
        tag = r.byte()
        if tag == END:
            return out
        if tag == LINE:
            opts = r.byte()
            r.nudge(opts)
            if opts & O_LINE_LSPACE:
                r.u16()
            if opts & O_LP_RULER:
                parse_ruler(r)
            n = Node('line')
            if opts & O_LINE_NULL:
                n.null = True
            else:
                n.items = parse_records(r)
            out.append(n)
        elif tag == CHAR:
            opts = r.byte()
            r.nudge(opts)
            n = Node('char')
            tf = r.byte()
            n.tf = tf - 128
            n.ch = None
            if not (opts & O_CHAR_ENC_NO_MTCODE):
                n.ch = r.u16()
            if opts & O_CHAR_ENC_CHAR_8:
                b = r.byte()
                if n.ch is None:
                    n.ch = b
            if opts & O_CHAR_ENC_CHAR_16:
                v = r.u16()
                if n.ch is None:
                    n.ch = v
            n.opts = opts
            if opts & O_CHAR_EMBELL:
                n.emb = [e for e in parse_records(r) if e.kind == 'embell']
            out.append(n)
        elif tag == TMPL:
            opts = r.byte()
            r.nudge(opts)
            n = Node('tmpl')
            n.sel = r.byte()
            v = r.byte()
            if v & 0x80:
                v = (v & 0x7F) | (r.byte() << 7)
            n.var = v
            r.byte()  # tùy chọn riêng của template
            n.items = parse_records(r)
            out.append(n)
        elif tag == PILE:
            opts = r.byte()
            r.nudge(opts)
            n = Node('pile')
            n.halign = r.byte()
            r.byte()  # valign
            if opts & O_LP_RULER:
                parse_ruler(r)
            n.items = parse_records(r)
            out.append(n)
        elif tag == MATRIX:
            opts = r.byte()
            r.nudge(opts)
            n = Node('matrix')
            r.byte(); n.halign = r.byte(); r.byte()  # valign, h_just, v_just
            n.rows, n.cols = r.byte(), r.byte()
            r.i += (2 * (n.rows + 1) + 7) // 8
            r.i += (2 * (n.cols + 1) + 7) // 8
            n.items = parse_records(r)
            out.append(n)
        elif tag == EMBELL:
            opts = r.byte()
            r.nudge(opts)
            n = Node('embell')
            n.sel = r.byte()
            out.append(n)
        elif tag == RULER:
            r.i -= 1
            r.byte()
            parse_ruler_body(r)
        elif tag == FONT_STYLE_DEF:
            r.byte(); r.byte()
        elif tag == SIZE:
            ls = r.byte()
            if ls == 101:
                r.u16()
            elif ls == 100:
                r.byte(); r.u16()
            else:
                r.byte()
        elif tag in (FULL, SUB, SUB2, SYM, SUBSYM):
            pass
        elif tag == COLOR:
            r.byte()
        elif tag == COLOR_DEF:
            opts = r.byte()
            r.i += 2 * (4 if opts & 0x01 else 3)
            if opts & 0x04:
                r.cstr()
        elif tag == FONT_DEF:
            r.byte(); r.cstr()
        elif tag == EQN_PREFS:
            r.byte()
            r.dims()
            r.dims()
            n = r.byte()
            for _ in range(n):
                if r.byte():
                    r.byte()
        elif tag == ENCODING_DEF:
            r.cstr()
        elif tag >= 100:
            ln = r.u16()
            r.i += ln
        else:
            raise MTEFError(f'record lạ {tag} tại {r.i - 1}')
    return out

def parse_ruler(r):
    tag = r.byte()
    if tag != RULER:
        r.i -= 1
        return
    parse_ruler_body(r)

def parse_ruler_body(r):
    n = r.byte()
    r.i += 3 * n

def parse_equation_native(blob):
    """blob = nội dung luồng 'Equation Native'. Trả về danh sách Node cấp cao nhất."""
    if len(blob) < 34:
        raise MTEFError('dữ liệu quá ngắn')
    hdr = struct.unpack_from('<H', blob, 0)[0]
    d = blob[hdr:]
    if d[0] != 5:
        raise MTEFError(f'MTEF phiên bản {d[0]} chưa hỗ trợ')
    r = Reader(d)
    r.i = 5
    r.cstr()      # application key, vd "DSMT7"
    r.byte()      # equation options
    return parse_records(r)

# ======================================================================= sang LaTeX

GREEK = {0x3B1: 'alpha', 0x3B2: 'beta', 0x3B3: 'gamma', 0x3B4: 'delta', 0x3B5: 'epsilon', 0x3B6: 'zeta',
         0x3B7: 'eta', 0x3B8: 'theta', 0x3B9: 'iota', 0x3BA: 'kappa', 0x3BB: 'lambda', 0x3BC: 'mu', 0x3BD: 'nu',
         0x3BE: 'xi', 0x3C0: 'pi', 0x3C1: 'rho', 0x3C3: 'sigma', 0x3C2: 'varsigma', 0x3C4: 'tau', 0x3C5: 'upsilon',
         0x3C6: 'varphi', 0x3D5: 'phi', 0x3C7: 'chi', 0x3C8: 'psi', 0x3C9: 'omega', 0x3D1: 'vartheta', 0x3F5: 'epsilon',
         0x393: 'Gamma', 0x394: 'Delta', 0x398: 'Theta', 0x39B: 'Lambda', 0x39E: 'Xi', 0x3A0: 'Pi', 0x3A3: 'Sigma',
         0x3A5: 'Upsilon', 0x3A6: 'Phi', 0x3A8: 'Psi', 0x3A9: 'Omega'}
SYM = {
    0x2264: r'\le', 0x2265: r'\ge', 0x2260: r'\ne', 0xB1: r'\pm', 0x2213: r'\mp', 0xD7: r'\times', 0xF7: r'\div',
    0x22C5: r'\cdot', 0xB7: r'\cdot', 0x2219: r'\cdot', 0x221E: r'\infty', 0x2208: r'\in', 0x2209: r'\notin',
    0x2282: r'\subset', 0x2283: r'\supset', 0x2286: r'\subseteq', 0x2287: r'\supseteq', 0x2284: r'\not\subset',
    0x222A: r'\cup', 0x2229: r'\cap', 0x2205: r'\varnothing', 0x2192: r'\to', 0x21D2: r'\Rightarrow',
    0x21D4: r'\Leftrightarrow', 0x21D0: r'\Leftarrow', 0x2194: r'\leftrightarrow', 0x2190: r'\leftarrow',
    0x2200: r'\forall', 0x2203: r'\exists', 0x2204: r'\nexists', 0x2220: r'\angle', 0x25B3: r'\triangle',
    0x2206: r'\Delta', 0xB0: r'^\circ', 0x2218: r'\circ', 0x2225: r'\parallel', 0x22A5: r'\perp', 0x2248: r'\approx',
    0x2261: r'\equiv', 0x223C: r'\sim', 0x2245: r'\cong', 0x2026: r'\ldots', 0x22EF: r'\cdots', 0x22EE: r'\vdots',
    0x2212: '-', 0x2032: "'", 0x2033: "''", 0x2016: r'\|', 0x2223: r'\mid', 0x2224: r'\nmid',
    0x211D: r'\mathbb{R}', 0x2115: r'\mathbb{N}', 0x2124: r'\mathbb{Z}', 0x211A: r'\mathbb{Q}', 0x2102: r'\mathbb{C}',
    0x2211: r'\sum', 0x220F: r'\prod', 0x222B: r'\int', 0x221A: r'\surd', 0x2234: r'\therefore', 0x2235: r'\because',
    0x226A: r'\ll', 0x226B: r'\gg', 0x2243: r'\simeq', 0x221D: r'\propto', 0x2227: r'\wedge', 0x2228: r'\vee',
    0xAC: r'\neg', 0x2192 + 0x10000: '', 0x27C2: r'\perp', 0x25CB: r'\circ', 0x2021: r'\ddagger', 0x2020: r'\dagger',
    0x2322: r'\frown', 0x2323: r'\smile', 0x2329: r'\langle', 0x232A: r'\rangle', 0x27E8: r'\langle', 0x27E9: r'\rangle',
    0x2245 + 0x10000: '', 0x22EE + 0x10000: '', 0x2061: '', 0x2062: '', 0x2063: '', 0x200B: '',
    0x2026 + 0x10000: '', 0x0394: r'\Delta', 0x2215: '/', 0x2044: '/', 0x226E: r'\nless', 0x226F: r'\ngtr',
}
ESC = {'{': r'\{', '}': r'\}', '%': r'\%', '#': r'\#', '&': r'\&', '_': r'\_', '$': r'\$', '\\': r'\backslash',
       '^': r'\hat{}', '~': r'\sim'}
FUNCS = {'sin', 'cos', 'tan', 'cot', 'log', 'ln', 'lim', 'max', 'min', 'exp', 'arcsin', 'arccos', 'arctan', 'sinh',
         'cosh', 'tanh', 'sec', 'csc', 'det', 'deg', 'dim', 'gcd', 'inf', 'sup', 'lg', 'ker'}
# MT Extra / ký tự riêng của MathType
PRIVATE = {0xEB1A: r'\overrightarrow{}', 0xEC09: r'\cdots', 0xEC0A: r'\cdots', 0xEC0B: r'\ddots', 0xEC0C: r'\vdots',
           0xEB00: '', 0xEB01: '', 0xEB02: '', 0xEB03: '', 0xEB04: '', 0xEB05: '', 0xEB06: '', 0xEB07: '', 0xEB08: '',
           0xF020: ' ', 0x2200 + 0x10000: '', 0xE98F: r'\varnothing', 0xE900: r'\triangle', 0xE901: r'\angle'}

def char_tex(n):
    c = n.ch
    if c is None:
        return ''
    if 0xEF00 <= c <= 0xEF0F or c in (0x2009, 0x200A, 0x2002, 0x2003, 0x2005, 0x2006, 0xA0):
        return r'\,' if c not in (0xEF04, 0x2003) else r'\quad '
    if c in PRIVATE:
        return PRIVATE[c]
    if c in GREEK:
        return '\\' + GREEK[c] + ' '
    if c in SYM:
        s = SYM[c]
        return s + (' ' if s.startswith('\\') and s[-1].isalpha() else '')
    ch = chr(c)
    if ch in ESC:
        return ESC[ch]
    if 0xE000 <= c <= 0xF8FF:
        return ''  # ký tự riêng không rõ: bỏ qua
    return ch

EMB = {2: r'\dot', 3: r'\ddot', 4: r'\dddot', 8: r'\tilde', 9: r'\hat', 11: r'\overrightarrow', 12: r'\overleftarrow',
       13: r'\overleftrightarrow', 14: r'\overrightarrow', 15: r'\overleftarrow', 17: r'\overline', 19: 'ARC', 20: 'ARC',
       24: r'\ddddot'}
PRIMES = {5: "'", 6: "''", 7: "'", 18: "'''"}

def apply_emb(base, embs):
    for e in embs:
        k = e.sel
        if k in PRIMES:
            base = '{' + base + '}' + PRIMES[k]
        elif k == 10:
            base = r'\not ' + base
        elif k in EMB:
            cmd = EMB[k]
            base = (r'\overset{\frown}{' + base + '}') if cmd == 'ARC' else (cmd + '{' + base + '}')
    return base

def line_tex(n):
    if n is None or n.null:
        return ''
    return items_tex(n.items)

def items_tex(items):
    out = []
    text_buf, func_buf = [], []

    def flush():
        if text_buf:
            s = ''.join(text_buf)
            if s.strip():
                out.append(r'\text{' + s.replace('\\', '').replace('{', '').replace('}', '') + '}')
            else:
                out.append(r'\ ' * len(s))
            text_buf.clear()
        if func_buf:
            w = ''.join(func_buf)
            out.append(('\\' + w + ' ') if w in FUNCS else (r'\operatorname{' + w + '}' if w.isalpha() and len(w) > 1 else w))
            func_buf.clear()

    for n in items:
        if n.kind == 'char':
            if n.tf == FN_TEXT and n.ch is not None and not n.emb and (chr(n.ch).isalpha() or chr(n.ch) == ' '
                                                                       or 0xC0 <= n.ch <= 0x1EF9):
                if func_buf:
                    flush()
                text_buf.append(chr(n.ch))
                continue
            if n.tf == FN_FUNCTION and n.ch is not None and chr(n.ch).isalpha() and not n.emb:
                if text_buf:
                    flush()
                if n.opts & O_CHAR_FUNC_START and func_buf:
                    flush()
                func_buf.append(chr(n.ch))
                continue
            flush()
            t = char_tex(n)
            if n.emb:
                t = apply_emb(t.strip(), n.emb)
            out.append(t)
        elif n.kind == 'tmpl':
            flush()
            out.append(tmpl_tex(n, out))
        elif n.kind == 'pile':
            flush()
            out.append(pile_tex(n))
        elif n.kind == 'matrix':
            flush()
            out.append(matrix_tex(n))
        elif n.kind == 'line':
            flush()
            out.append(line_tex(n))
    flush()
    return ''.join(out)

def pile_tex(n):
    rows = [line_tex(x) for x in n.items if x.kind == 'line']
    if len(rows) == 1:
        return rows[0]
    al = {1: 'l', 2: 'c', 3: 'r', 4: 'l', 5: 'r'}.get(n.halign, 'l')
    return r'\begin{array}{' + al + '}' + r' \\ '.join(rows) + r'\end{array}'

def matrix_tex(n):
    cells = [line_tex(x) for x in n.items if x.kind == 'line']
    rows = [' & '.join(cells[i * n.cols:(i + 1) * n.cols]) for i in range(n.rows)]
    return r'\begin{matrix}' + r' \\ '.join(rows) + r'\end{matrix}'

FENCE = {'(': '(', ')': ')', '[': '[', ']': ']', '{': r'\{', '}': r'\}', '|': '|', '‖': r'\|', '⟨': r'\langle',
         '⟩': r'\rangle', '〈': r'\langle', '〉': r'\rangle', '⌊': r'\lfloor', '⌋': r'\rfloor', '⌈': r'\lceil',
         '⌉': r'\rceil', '⟦': '[', '⟧': ']'}
DEFAULT_FENCES = {0: ('\\langle', '\\rangle'), 1: ('(', ')'), 2: ('\\{', '\\}'), 3: ('[', ']'), 4: ('|', '|'),
                  5: ('\\|', '\\|'), 6: ('\\lfloor', '\\rfloor'), 7: ('\\lceil', '\\rceil'), 8: ('[', ']'), 9: ('(', ')')}
BIGOP = {15: r'\int', 16: r'\sum', 17: r'\prod', 18: r'\coprod', 19: r'\bigcup', 20: r'\bigcap', 21: r'\int', 22: r'\sum'}

def tmpl_tex(n, prev_out):
    sel, var = n.sel, n.var
    lines = [x for x in n.items if x.kind in ('line', 'pile', 'matrix')]
    chars = [x for x in n.items if x.kind == 'char']
    L = lambda k: (line_tex(lines[k]) if lines[k].kind == 'line' else
                   (pile_tex(lines[k]) if lines[k].kind == 'pile' else matrix_tex(lines[k]))) if k < len(lines) else ''

    if sel <= 9:  # các loại ngoặc
        body = L(0)
        fl = [FENCE.get(chr(c.ch), char_tex(c).strip()) for c in chars if c.ch]
        dl, dr = DEFAULT_FENCES.get(sel, ('(', ')'))
        has_l = bool(var & 0x01) if sel != 9 else True
        has_r = bool(var & 0x02) if sel != 9 else True
        if sel == 9:   # khoảng: ký hiệu lấy từ các CHAR
            left = fl[0] if len(fl) > 0 else '['
            right = fl[1] if len(fl) > 1 else ']'
        else:
            left = (fl.pop(0) if fl else dl) if has_l else '.'
            right = (fl.pop(0) if fl else dr) if has_r else '.'
        return r'\left' + left + ' ' + body + r' \right' + right + ' '
    if sel == 10:  # căn
        rad, idx = L(0), L(1)
        return (r'\sqrt[' + idx + ']{' + rad + '}') if idx.strip() else (r'\sqrt{' + rad + '}')
    if sel == 11:  # phân số
        num, den = L(0), L(1)
        if var & 0x02 and not var & 0x01:  # dạng gạch chéo
            return '{' + num + '}/{' + den + '}'
        return r'\frac{' + num + '}{' + den + '}'
    if sel == 12:
        return r'\underline{' + L(0) + '}'
    if sel == 13:
        return r'\overline{' + L(0) + '}'
    if sel == 14:  # mũi tên có chữ
        top, bot = L(0), L(1)
        return r'\xrightarrow[' + bot + ']{' + top + '}' if bot.strip() else r'\xrightarrow{' + top + '}'
    if sel in BIGOP:
        main, lo, up = L(0), L(1), L(2)
        op = BIGOP[sel]
        if chars and chars[-1].ch:
            t = char_tex(chars[-1]).strip()
            if t.startswith('\\'):
                op = t
        s = op
        if lo.strip():
            s += '_{' + lo + '}'
        if up.strip():
            s += '^{' + up + '}'
        return s + ' ' + main
    if sel == 23:  # lim
        main, lo, up = L(0), L(1), L(2)
        s = main.strip() or r'\lim'
        if lo.strip():
            s += r'\limits_{' + lo + '}'
        if up.strip():
            s += '^{' + up + '}'
        return s + ' '
    if sel in (24, 25):  # ngoặc nhọn ngang
        main, lab = L(0), L(1)
        top = bool(var & 0x01)
        cmd = (r'\overbrace' if top else r'\underbrace') if sel == 24 else (r'\overbrace' if top else r'\underbrace')
        return cmd + '{' + main + '}' + (('^' if top else '_') + '{' + lab + '}' if lab.strip() else '')
    if sel == 26:  # chia dài
        return L(0)
    if sel in (27, 28, 29):  # chỉ số dưới / trên
        sub, sup = L(0), L(1)
        if sel == 27:
            sup = ''
        if sel == 28:
            sup, sub = (sup or sub), ''
            if not sup and len(lines) == 1:
                sup = L(0)
        base = '' if prev_out else '{}'
        s = base
        if sub.strip():
            s += '_{' + sub + '}'
        if sup.strip():
            s += '^{' + sup + '}'
        return s
    if sel == 30:
        return r'\left\langle ' + L(0) + r' \right|'
    if sel == 31:  # vectơ (mũi tên trên)
        if var & 0x0008:  # dưới
            return r'\underrightarrow{' + L(0) + '}'
        if (var & 0x03) == 0x01:
            return r'\overleftarrow{' + L(0) + '}'
        if (var & 0x03) == 0x03:
            return r'\overleftrightarrow{' + L(0) + '}'
        return r'\overrightarrow{' + L(0) + '}'
    if sel == 32:
        return r'\widetilde{' + L(0) + '}'
    if sel == 33:
        return r'\widehat{' + L(0) + '}'
    if sel == 34:
        return r'\overset{\frown}{' + L(0) + '}'
    if sel in (35, 36, 37):
        return L(0)
    # template lạ: ghép nội dung
    return ''.join(L(k) for k in range(len(lines)))

def to_latex(blob):
    nodes = parse_equation_native(blob)
    s = items_tex(nodes)
    return ' '.join(s.split())

def latex_from_ole(path_or_bytes):
    import io
    import olefile
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray)) else path_or_bytes
    o = olefile.OleFileIO(src)
    try:
        blob = o.openstream('Equation Native').read()
    finally:
        o.close()
    return to_latex(blob)

# ======================================================================= sang Equation của Word (OMML)
from lxml import etree as _et

_M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def _m(tag, attrs=None, kids=()):
    e = _et.Element('{%s}%s' % (_M, tag))
    for k, v in (attrs or {}).items():
        e.set('{%s}%s' % (_M, k), v)
    for c in kids:
        if c is not None:
            e.append(c)
    return e

def _val(tag, v):
    return _m(tag, {'val': v})

UNI = {0x2212: '−', 0xEF00: ' ', 0xEF01: ' ', 0xEF02: ' ', 0xEF03: ' ', 0xEF04: ' ',
       0xEF05: ' ', 0xEF08: ' ', 0xEC09: '⋯', 0xEC0A: '⋯', 0xEC0B: '⋱', 0xEC0C: '⋮'}

def _run(text, style=None, normal=False):
    r = _m('r')
    if normal or style:
        rp = _m('rPr')
        if normal:
            rp.append(_m('nor'))
        elif style:
            rp.append(_val('sty', style))
        r.append(rp)
    if normal:
        wr = _et.SubElement(r, '{%s}rPr' % _W)
        f = _et.SubElement(wr, '{%s}rFonts' % _W)
        f.set('{%s}ascii' % _W, 'Times New Roman'); f.set('{%s}hAnsi' % _W, 'Times New Roman')
    t = _et.SubElement(r, '{%s}t' % _M)
    t.text = text
    if text != text.strip():
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    return r

def _char_text(n):
    c = n.ch
    if c is None:
        return ''
    if c in UNI:
        return UNI[c]
    if 0xE000 <= c <= 0xF8FF:
        return ''
    return chr(c)

def _e(kids):
    return _m('e', kids=kids)

ACC = {2: '̇', 3: '̈', 4: '⃛', 8: '̃', 9: '̂', 11: '⃗', 12: '⃖', 13: '⃡',
       14: '⃗', 15: '⃖', 19: '⏜', 20: '⏝', 24: '⃜'}

def _emb_omml(base_runs, embs):
    cur = base_runs
    for e in embs:
        k = e.sel
        if k in PRIMES:
            cur = [_m('sSup', kids=[_e(cur), _m('sup', kids=[_run('′' * len(PRIMES[k]), 'p')])])]
        elif k == 10:  # gạch chéo (không thuộc…)
            if len(cur) == 1 and cur[0].findtext('{%s}t' % _M) == '∈':
                cur = [_run('∉')]
            else:
                txt = ''.join(t.text or '' for r in cur for t in r.iter('{%s}t' % _M))
                cur = [_run(txt + '̸')]
        elif k == 17:
            cur = [_m('bar', kids=[_m('barPr', kids=[_val('pos', 'top')]), _e(cur)])]
        elif k in ACC:
            cur = [_m('acc', kids=[_m('accPr', kids=[_val('chr', ACC[k])]), _e(cur)])]
    return cur

def _line(n):
    if n is None or getattr(n, 'null', False):
        return []
    if n.kind == 'pile':
        return [_pile(n)]
    if n.kind == 'matrix':
        return [_matrix(n)]
    return _items(n.items)

def _items(items):
    out = []
    text, func = [], []

    def flush():
        if text:
            out.append(_run(''.join(text), normal=True))
            text.clear()
        if func:
            out.append(_run(''.join(func), 'p'))
            func.clear()

    for n in items:
        if n.kind == 'char':
            ch = _char_text(n)
            if n.tf == FN_TEXT and ch and not n.emb and (ch.isalpha() or ch == ' ' or 0xC0 <= n.ch <= 0x1EF9):
                if func:
                    flush()
                text.append(ch)
                continue
            if n.tf == FN_FUNCTION and ch.isalpha() and not n.emb:
                if text:
                    flush()
                if n.opts & O_CHAR_FUNC_START and func:
                    flush()
                func.append(ch)
                continue
            flush()
            if not ch:
                continue
            if ch == ' ':
                ch = '\u2005'          # dấu cách trong công thức (Word bỏ qua dấu cách thường)
            elif ch == '*':
                ch = '\u2217'
            style = None
            if ch.isalpha() and not (n.tf in (FN_VARIABLE, FN_LCGREEK) or n.tf < 0):
                style = 'p'
            if n.tf == FN_VECTOR:
                style = 'b'
            runs = [_run(ch, style)]
            if n.emb:
                runs = _emb_omml(runs, n.emb)
            out.extend(runs)
        elif n.kind == 'tmpl':
            flush()
            _tmpl(n, out)
        elif n.kind == 'pile':
            flush()
            out.append(_pile(n))
        elif n.kind == 'matrix':
            flush()
            out.append(_matrix(n))
        elif n.kind == 'line':
            flush()
            out.extend(_line(n))
    flush()
    return out

def _pile(n):
    rows = [x for x in n.items if x.kind == 'line']
    if len(rows) == 1:
        return _m('box', kids=[_e(_line(rows[0]))])
    jc = {1: 'left', 3: 'right'}.get(n.halign)
    pr = _m('eqArrPr', kids=[_val('baseJc', 'center')])
    arr = _m('eqArr', kids=[pr] + [_e(_line(r)) for r in rows])
    return arr

def _matrix(n):
    cells = [x for x in n.items if x.kind == 'line']
    m = _m('m')
    for i in range(n.rows):
        mr = _m('mr', kids=[_e(_line(c)) for c in cells[i * n.cols:(i + 1) * n.cols]])
        m.append(mr)
    return m

FENCE_U = {0: ('⟨', '⟩'), 1: ('(', ')'), 2: ('{', '}'), 3: ('[', ']'), 4: ('|', '|'), 5: ('‖', '‖'),
           6: ('⌊', '⌋'), 7: ('⌈', '⌉'), 8: ('⟦', '⟧'), 9: ('(', ')')}
NARY = {15: '∫', 16: '∑', 17: '∏', 18: '∐', 19: '⋃', 20: '⋂', 21: '∫', 22: '∑'}

def _tmpl(n, out):
    sel, var = n.sel, n.var
    subs = [x for x in n.items if x.kind in ('line', 'pile', 'matrix')]
    chars = [x for x in n.items if x.kind == 'char']
    S = lambda k: _line(subs[k]) if k < len(subs) else []
    empty = lambda k: k >= len(subs) or getattr(subs[k], 'null', False) or not _line(subs[k])

    if sel <= 9:
        fl = [_char_text(c) for c in chars if c.ch]
        dl, dr = FENCE_U.get(sel, ('(', ')'))
        if sel == 9:
            left, right = (fl + ['[', ']'])[:2] if len(fl) >= 2 else (dl, dr)
        else:
            left = (fl.pop(0) if fl else dl) if var & 0x01 else ''
            right = (fl.pop(0) if fl else dr) if var & 0x02 else ''
        pr = _m('dPr', kids=[_val('begChr', left), _val('endChr', right)])
        out.append(_m('d', kids=[pr, _e(S(0))]))
    elif sel == 10:
        if empty(1):
            out.append(_m('rad', kids=[_m('radPr', kids=[_val('degHide', '1')]), _m('deg'), _e(S(0))]))
        else:
            out.append(_m('rad', kids=[_m('deg', kids=S(1)), _e(S(0))]))
    elif sel == 11:
        kids = [_m('num', kids=S(0)), _m('den', kids=S(1))]
        if var & 0x02 and not var & 0x01:
            kids.insert(0, _m('fPr', kids=[_val('type', 'lin')]))
        out.append(_m('f', kids=kids))
    elif sel in (12, 13):
        out.append(_m('bar', kids=[_m('barPr', kids=[_val('pos', 'bot' if sel == 12 else 'top')]), _e(S(0))]))
    elif sel == 14:
        out.append(_m('groupChr', kids=[_m('groupChrPr', kids=[_val('chr', '→'), _val('pos', 'top'), _val('vertJc', 'bot')]),
                                         _e(S(0) or [_run(' ')])]))
    elif sel in NARY:
        ch = NARY[sel]
        if chars and chars[-1].ch:
            ch = _char_text(chars[-1]) or ch
        pr = _m('naryPr', kids=[_val('chr', ch), _val('limLoc', 'subSup' if sel in (15, 21) else 'undOvr')])
        if empty(1):
            pr.append(_val('subHide', '1'))
        if empty(2):
            pr.append(_val('supHide', '1'))
        out.append(_m('nary', kids=[pr, _m('sub', kids=S(1)), _m('sup', kids=S(2)), _e(S(0))]))
    elif sel == 23:
        main = S(0) or [_run('lim', 'p')]
        out.append(_m('limLow', kids=[_e(main), _m('lim', kids=S(1))]))
    elif sel in (24, 25):
        top = bool(var & 0x01)
        ch = ('⏞' if top else '⏟') if sel == 24 else ('⎴' if top else '⎵')
        g = _m('groupChr', kids=[_m('groupChrPr', kids=[_val('chr', ch), _val('pos', 'top' if top else 'bot')]), _e(S(0))])
        if not empty(1):
            g = _m('limUpp' if top else 'limLow', kids=[_e([g]), _m('lim', kids=S(1))])
        out.append(g)
    elif sel == 26:
        out.extend(S(0))
    elif sel in (27, 28, 29):
        sub, sup = S(0), S(1)
        if sel == 27:
            sup = []
        elif sel == 28:
            sup, sub = (sup or sub), []
        base = [out.pop()] if out else [_run('​')]
        if sub and sup:
            out.append(_m('sSubSup', kids=[_e(base), _m('sub', kids=sub), _m('sup', kids=sup)]))
        elif sup:
            out.append(_m('sSup', kids=[_e(base), _m('sup', kids=sup)]))
        elif sub:
            out.append(_m('sSub', kids=[_e(base), _m('sub', kids=sub)]))
        else:
            out.extend(base)
    elif sel == 31:
        ch = '⃗'
        if (var & 0x03) == 0x01:
            ch = '⃖'
        elif (var & 0x03) == 0x03:
            ch = '⃡'
        out.append(_m('acc', kids=[_m('accPr', kids=[_val('chr', ch)]), _e(S(0))]))
    elif sel in (32, 33, 34):
        ch = {32: '̃', 33: '̂', 34: '⏜'}[sel]
        out.append(_m('acc', kids=[_m('accPr', kids=[_val('chr', ch)]), _e(S(0))]))
    else:
        for k in range(len(subs)):
            out.extend(S(k))

def _merge_runs(el):
    """Gộp các m:r liền nhau cùng kiểu chữ cho gọn."""
    for parent in [el] + list(el.iter()):
        kids = list(parent)
        prev = None
        for k in kids:
            if k.tag == '{%s}r' % _M:
                sig = _et.tostring(k.find('{%s}rPr' % _M)) if k.find('{%s}rPr' % _M) is not None else b''
                sig += _et.tostring(k.find('{%s}rPr' % _W)) if k.find('{%s}rPr' % _W) is not None else b''
                if prev is not None and prev[1] == sig:
                    t0, t1 = prev[0].find('{%s}t' % _M), k.find('{%s}t' % _M)
                    t0.text = (t0.text or '') + (t1.text or '')
                    if t0.text != t0.text.strip():
                        t0.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                    parent.remove(k)
                    continue
                prev = (k, sig)
            else:
                prev = None

def to_omml(blob):
    """Trả về phần tử <m:oMath> tương ứng với công thức."""
    nodes = parse_equation_native(blob)
    om = _m('oMath', kids=_items(nodes))
    _merge_runs(om)
    return om
