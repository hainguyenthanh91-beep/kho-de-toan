"""Đổi mọi công thức MathType trong file .docx sang Equation của Word (OMML).

Giữ nguyên chữ, hình, bảng; chỉ thay đối tượng MathType bằng công thức tương đương.
Công thức nào không đọc được thì giữ lại bản MathType gốc.
"""
import io, posixpath, re, zipfile
from lxml import etree
from . import mtef

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
O = 'urn:schemas-microsoft-com:office:office'
V = 'urn:schemas-microsoft-com:vml'
PR = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
NS = {'w': W, 'r': R, 'o': O, 'v': V}

PARTS = re.compile(r'^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$')

def _rels_path(part):
    d, f = posixpath.split(part)
    return posixpath.join(d, '_rels', f + '.rels')

MNS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'

def _apply_size(om, run):
    """Cỡ chữ công thức = cỡ chữ của dòng chứa nó (MathType nằm trong run có w:sz)."""
    sz = run.find('w:rPr/w:sz', NS)
    if sz is None:
        return
    val = sz.get('{%s}val' % W)
    for r in om.iter('{%s}r' % MNS):
        wr = r.find('{%s}rPr' % W)
        if wr is None:
            wr = etree.Element('{%s}rPr' % W)
            t = r.find('{%s}t' % MNS)
            r.insert(r.index(t), wr)
        for tag in ('sz', 'szCs'):
            e = wr.find('{%s}%s' % (W, tag))
            if e is None:
                e = etree.SubElement(wr, '{%s}%s' % (W, tag))
            e.set('{%s}val' % W, val)

def convert_docx(data: bytes):
    zin = zipfile.ZipFile(io.BytesIO(data))
    files = {n: zin.read(n) for n in zin.namelist()}
    stats = {'total': 0, 'converted': 0, 'failed': 0, 'equation3': 0}
    removed_targets = set()
    for part in [n for n in files if PARTS.match(n)]:
        rp = _rels_path(part)
        if rp not in files:
            continue
        rels = etree.fromstring(files[rp])
        rmap = {r.get('Id'): r for r in rels}
        root = etree.fromstring(files[part])
        changed = False
        drop_ids = set()
        for obj in list(root.iter('{%s}object' % W)):
            ole = obj.find('o:OLEObject', NS)
            if ole is None:
                continue
            prog = ole.get('ProgID') or ''
            if not prog.startswith('Equation.'):
                continue
            stats['total'] += 1
            if not prog.startswith('Equation.DSMT'):
                stats['equation3'] += 1
                stats['failed'] += 1
                continue
            rid = ole.get('{%s}id' % R)
            rel = rmap.get(rid)
            if rel is None:
                stats['failed'] += 1
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(part), rel.get('Target')))
            try:
                import olefile
                o = olefile.OleFileIO(io.BytesIO(files[target]))
                blob = o.openstream('Equation Native').read()
                o.close()
                om = mtef.to_omml(blob)
            except Exception:
                stats['failed'] += 1
                continue
            run = obj.getparent()
            if run is None or run.tag != '{%s}r' % W:
                stats['failed'] += 1
                continue
            _apply_size(om, run)
            parent = run.getparent()
            pos = parent.index(run)
            others = [c for c in run if c.tag not in ('{%s}rPr' % W, '{%s}object' % W)]
            if others:  # tách: phần còn lại của run giữ nguyên, chèn công thức ngay sau
                run.remove(obj)
                parent.insert(pos + 1, om)
            else:
                parent.remove(run)
                parent.insert(pos, om)
            # các rId không còn dùng
            drop_ids.add(rid)
            for im in obj.iter('{%s}imagedata' % V):
                if im.get('{%s}id' % R):
                    drop_ids.add(im.get('{%s}id' % R))
            stats['converted'] += 1
            changed = True
        if changed:
            xml_now = etree.tostring(root, encoding='unicode')
            for rid in drop_ids:
                if f'"{rid}"' in xml_now:
                    continue
                rel = rmap.get(rid)
                if rel is not None:
                    removed_targets.add(posixpath.normpath(posixpath.join(posixpath.dirname(part), rel.get('Target'))))
                    rels.remove(rel)
            files[part] = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            files[rp] = etree.tostring(rels, xml_declaration=True, encoding='UTF-8', standalone=True)
    # xoá tệp không còn ai dùng
    still = b''.join(v for k, v in files.items() if k.endswith('.rels'))
    for t in removed_targets:
        if posixpath.basename(t).encode() not in still:
            files.pop(t, None)
    if removed_targets and '[Content_Types].xml' in files:
        ct = etree.fromstring(files['[Content_Types].xml'])
        for ov in list(ct.findall('{%s}Override' % CT)):
            if ov.get('PartName', '').lstrip('/') in removed_targets and ov.get('PartName', '').lstrip('/') not in files:
                ct.remove(ov)
        files['[Content_Types].xml'] = etree.tostring(ct, xml_declaration=True, encoding='UTF-8', standalone=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for n in zin.namelist():
            if n in files:
                z.writestr(n, files[n])
    return buf.getvalue(), stats

def count_mathtype(data: bytes):
    z = zipfile.ZipFile(io.BytesIO(data))
    n = 0
    for name in z.namelist():
        if PARTS.match(name):
            n += len(re.findall(rb'ProgID="Equation\.', z.read(name)))
    return n
