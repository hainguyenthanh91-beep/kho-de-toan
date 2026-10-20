"""Chuyển công thức Word (OMML) sang LaTeX để hiển thị trên web (KaTeX) và để tìm kiếm.
Chỉ dùng cho XEM TRƯỚC — file Word xuất ra luôn dùng công thức gốc."""
from lxml import etree

M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def _ln(e):
    return etree.QName(e).localname if isinstance(e.tag, str) else ''

def _ns(e):
    return etree.QName(e).namespace if isinstance(e.tag, str) else ''

SYM = {
    '≤': r'\le ', '≥': r'\ge ', '≠': r'\ne ', '±': r'\pm ', '∓': r'\mp ', '×': r'\times ', '÷': r'\div ',
    '⋅': r'\cdot ', '·': r'\cdot ', '∞': r'\infty ', '∈': r'\in ', '∉': r'\notin ', '⊂': r'\subset ',
    '⊃': r'\supset ', '⊆': r'\subseteq ', '⊄': r'\not\subset ', '∪': r'\cup ', '∩': r'\cap ', '∅': r'\varnothing ',
    '⌀': r'\varnothing ', '→': r'\to ', '⇒': r'\Rightarrow ', '⇔': r'\Leftrightarrow ', '⇐': r'\Leftarrow ',
    '∀': r'\forall ', '∃': r'\exists ', '∠': r'\angle ', '△': r'\triangle ', '∆': r'\Delta ', '°': r'^\circ ',
    '∥': r'\parallel ', '⊥': r'\perp ', '≈': r'\approx ', '≡': r'\equiv ', '∼': r'\sim ', '…': r'\ldots ',
    '⋮': r'\vdots ', '−': '-', 'α': r'\alpha ', 'β': r'\beta ', 'γ': r'\gamma ', 'δ': r'\delta ', 'ε': r'\varepsilon ',
    'φ': r'\varphi ', 'π': r'\pi ', 'θ': r'\theta ', 'λ': r'\lambda ', 'μ': r'\mu ', 'σ': r'\sigma ', 'ω': r'\omega ',
    'Ω': r'\Omega ', 'ρ': r'\rho ', 'Φ': r'\Phi ', 'Σ': r'\Sigma ', 'ℝ': r'\mathbb{R}', 'ℕ': r'\mathbb{N}',
    'ℤ': r'\mathbb{Z}', 'ℚ': r'\mathbb{Q}', 'ℂ': r'\mathbb{C}', '{': r'\{', '}': r'\}', '%': r'\%', '#': r'\#',
    '&': r'\&', '_': r'\_', '$': r'\$', '∘': r'\circ ', '′': "'", '″': "''", '⟂': r'\perp ', ' ': ' ', ' ': ' ',
    '∫': r'\int ', '∑': r'\sum ', '∏': r'\prod ', '√': r'\surd ', '|': '|', '⇀': r'\rightharpoonup ',
}
FUNCS = {'sin', 'cos', 'tan', 'cot', 'log', 'ln', 'lim', 'max', 'min', 'exp'}

def _txt(s):
    return ''.join(SYM.get(ch, ch) for ch in s)

def _chr(e, tag, default):
    for c in e:
        if _ln(c).endswith('Pr'):
            for p in c:
                if _ln(p) == tag:
                    return p.get('{%s}val' % M, '')
    return default

DELIM = {'(': '(', ')': ')', '[': '[', ']': ']', '{': r'\{', '}': r'\}', '|': '|', '‖': r'\|',
         '⌊': r'\lfloor ', '⌋': r'\rfloor ', '⌈': r'\lceil ', '⌉': r'\rceil ', '〈': r'\langle ', '〉': r'\rangle ',
         '⟨': r'\langle ', '⟩': r'\rangle ', '': '.'}

def _child(e, name):
    for c in e:
        if _ln(c) == name:
            return c
    return None

def conv(e):
    """Chuyển một phần tử OMML (hoặc danh sách con) thành LaTeX."""
    name = _ln(e)
    if name in ('oMath', 'e', 'num', 'den', 'sub', 'sup', 'deg', 'fName', 'lim', 'oMathPara'):
        return ''.join(conv(c) for c in e)
    if name == 'r':
        t = ''.join(x.text or '' for x in e if _ln(x) == 't')
        if not t:
            return ''
        plain = False
        rpr = _child(e, 'rPr')
        if rpr is not None:
            for p in rpr:
                if _ln(p) == 'sty' and p.get('{%s}val' % M) == 'p':
                    plain = True
                if _ln(p) == 'nor':
                    plain = True
        if t.strip() in FUNCS:
            return '\\' + t.strip() + ' '
        if plain and any(ch.isalpha() and ch.isascii() for ch in t) and len(t.strip()) > 1:
            return r'\text{' + t + '}'
        return _txt(t)
    if name == 'f':
        typ = _chr(e, 'type', 'bar')
        n, d = conv(_child(e, 'num')), conv(_child(e, 'den'))
        if typ == 'lin':
            return n + '/' + d
        if typ == 'noBar':
            return r'\genfrac{}{}{0pt}{}{' + n + '}{' + d + '}'
        return r'\frac{' + n + '}{' + d + '}'
    if name == 'sSup':
        return '{' + conv(_child(e, 'e')) + '}^{' + conv(_child(e, 'sup')) + '}'
    if name == 'sSub':
        return '{' + conv(_child(e, 'e')) + '}_{' + conv(_child(e, 'sub')) + '}'
    if name == 'sSubSup':
        return '{' + conv(_child(e, 'e')) + '}_{' + conv(_child(e, 'sub')) + '}^{' + conv(_child(e, 'sup')) + '}'
    if name == 'sPre':
        return '{}_{' + conv(_child(e, 'sub')) + '}^{' + conv(_child(e, 'sup')) + '}' + conv(_child(e, 'e'))
    if name == 'rad':
        deg = _child(e, 'deg')
        dg = conv(deg) if deg is not None else ''
        body = conv(_child(e, 'e'))
        return (r'\sqrt[' + dg + ']{' + body + '}') if dg.strip() else (r'\sqrt{' + body + '}')
    if name == 'd':
        beg, end, sep = _chr(e, 'begChr', '('), _chr(e, 'endChr', ')'), _chr(e, 'sepChr', '|')
        parts = [conv(c) for c in e if _ln(c) == 'e']
        inner = (' ' + DELIM.get(sep, sep) + ' ').join(parts)
        return r'\left' + DELIM.get(beg, beg) + inner + r'\right' + DELIM.get(end, end)
    if name == 'nary':
        ch = _chr(e, 'chr', '∫')
        op = {'∑': r'\sum', '∏': r'\prod', '∫': r'\int', '∬': r'\iint', '∮': r'\oint', '⋃': r'\bigcup', '⋂': r'\bigcap'}.get(ch, r'\int')
        sub, sup = _child(e, 'sub'), _child(e, 'sup')
        s = op
        if sub is not None and conv(sub):
            s += '_{' + conv(sub) + '}'
        if sup is not None and conv(sup):
            s += '^{' + conv(sup) + '}'
        return s + ' ' + conv(_child(e, 'e'))
    if name == 'func':
        fn = conv(_child(e, 'fName')).strip()
        if fn and not fn.startswith('\\') and fn.isalpha():
            fn = r'\operatorname{' + fn + '}'
        return fn + ' ' + conv(_child(e, 'e'))
    if name == 'limLow':
        return conv(_child(e, 'e')) + '_{' + conv(_child(e, 'lim')) + '}'
    if name == 'limUpp':
        return conv(_child(e, 'e')) + '^{' + conv(_child(e, 'lim')) + '}'
    if name == 'acc':
        ch = _chr(e, 'chr', '̂')
        cmd = {'⃗': r'\overrightarrow', '→': r'\overrightarrow', '̂': r'\widehat', '^': r'\widehat',
               '̃': r'\widetilde', '̄': r'\overline', '̅': r'\overline', '̇': r'\dot', '̈': r'\ddot',
               '⃖': r'\overleftarrow', '←': r'\overleftarrow'}.get(ch, r'\widehat')
        return cmd + '{' + conv(_child(e, 'e')) + '}'
    if name == 'bar':
        pos = _chr(e, 'pos', 'bot')
        return (r'\overline{' if pos == 'top' else r'\underline{') + conv(_child(e, 'e')) + '}'
    if name == 'groupChr':
        ch, pos = _chr(e, 'chr', '⏟'), _chr(e, 'pos', 'bot')
        body = conv(_child(e, 'e'))
        if ch in ('→', '⃗'):
            return r'\overrightarrow{' + body + '}'
        return (r'\underbrace{' if pos == 'bot' else r'\overbrace{') + body + '}'
    if name == 'eqArr':
        rows = [conv(c) for c in e if _ln(c) == 'e']
        return r'\begin{matrix}' + r'\\'.join(rows) + r'\end{matrix}'
    if name == 'm':
        rows = []
        for mr in e:
            if _ln(mr) == 'mr':
                rows.append(' & '.join(conv(c) for c in mr if _ln(c) == 'e'))
        return r'\begin{matrix}' + r'\\'.join(rows) + r'\end{matrix}'
    if name in ('box', 'borderBox', 'phant'):
        return conv(_child(e, 'e'))
    if name.endswith('Pr') or name in ('ctrlPr', 'argPr'):
        return ''
    # thẻ không biết: lấy nội dung con
    return ''.join(conv(c) for c in e)

def to_latex(omath):
    s = conv(omath)
    # \left\{ ... \right. hay gặp ở hệ phương trình
    return ' '.join(s.split())

def to_plain(omath):
    """Văn bản thô để tìm kiếm."""
    return ''.join(t.text or '' for t in omath.iter('{%s}t' % M))
