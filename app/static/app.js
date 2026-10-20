'use strict';
/* ================= tiện ích ================= */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const TYPES = [['TN','Trắc nghiệm'],['ĐS','Đúng/Sai'],['TLN','Trả lời ngắn'],['TL','Tự luận']];
const TYPE_NAME = Object.fromEntries(TYPES);
const LEVELS = [['M1','Nhận biết'],['M2','Thông hiểu'],['M3','Vận dụng'],['M4','Vận dụng cao']];
const LV_NAME = Object.fromEntries(LEVELS);
const MXCOLS = [...LEVELS, ['ANY', 'Mức bất kỳ']];
const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI'];
const norm = s => (s || '').toLowerCase().replace(/đ/g, 'd').normalize('NFD').replace(/[\u0300-\u036f]/g, '');

const OFFLINE = 'Không kết nối được với phần mềm. Kiểm tra cửa sổ đen (máy chủ) còn đang chạy không, rồi tải lại trang (F5).';
async function api(path, opts = {}) {
  let r;
  try { r = await fetch(path, {headers: opts.body && !(opts.body instanceof FormData) ? {'Content-Type': 'application/json'} : {}, ...opts}); }
  catch (_) { throw new Error(OFFLINE); }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || JSON.stringify(j); } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}
const post = (u, b, m = 'POST') => api(u, {method: m, body: JSON.stringify(b)});
function toast(msg, ms = 2400) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('show'), ms);
}
function renderMath(root) {
  $$('.tex', root).forEach(el => {
    if (el.dataset.done) return;
    try { katex.render(el.textContent, el, {throwOnError: false, displayMode: el.classList.contains('tex-d')}); } catch (_) {}
    el.dataset.done = 1;
  });
}
function store(key, val) { try { if (val === undefined) return JSON.parse(localStorage.getItem(key)); localStorage.setItem(key, JSON.stringify(val)); } catch (_) { return null; } }
const DESK = () => window.pywebview && window.pywebview.api;
/* Tải file: trong ứng dụng PC thì hỏi nơi lưu bằng hộp thoại Windows; trong trình duyệt thì tải bình thường. */
async function download(url, body, fallbackName) {
  if (DESK()) {
    const r = await window.pywebview.api.save(url, body ? 'POST' : 'GET', body ?? null, fallbackName);
    if (r.cancel) return null;
    if (!r.ok) { const e = new Error((r.body && r.body.detail) || r.error || 'Có lỗi khi tạo file'); e.status = r.status; e.body = r.body; throw e; }
    savedToast(r.path);
    return {name: r.path.split(/[\\/]/).pop(), path: r.path};
  }
  let r;
  try { r = body ? await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}) : await fetch(url); }
  catch (_) { throw new Error(OFFLINE); }
  if (!r.ok) { const j = await r.json().catch(() => ({})); const e = new Error(j.detail || r.statusText); e.status = r.status; e.body = j; throw e; }
  const blob = await r.blob();
  const name = (r.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || fallbackName;
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  return {name};
}
function savedToast(path) {
  const t = document.createElement('div');
  t.className = 'toast show act';
  t.innerHTML = `<span>Đã lưu <b>${esc(path.split(/[\\/]/).pop())}</b></span><button data-k="open">Mở file</button><button data-k="dir">Mở thư mục</button><button data-k="x" aria-label="Đóng">✕</button>`;
  document.body.appendChild(t);
  const close = () => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); };
  t.onclick = e => {
    const k = e.target.dataset.k; if (!k) return;
    if (k === 'open') window.pywebview.api.open_path(path);
    if (k === 'dir') window.pywebview.api.reveal(path);
    close();
  };
  setTimeout(close, 9000);
}
const lvButtons = (cur, short) => `<div class="lvset">${LEVELS.map(([k], i) => `<button data-lv="${k}" class="${k === cur ? 'on' : ''}" title="Mức ${i + 1} · ${LV_NAME[k]} (phím ${i + 1})">${short ? 'M' + (i + 1) : 'Mức ' + (i + 1)}</button>`).join('')}</div>`;
const ICON_FOLDER = '<svg class="ico" width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><path fill="#E8A200" d="M3 6.5A1.5 1.5 0 0 1 4.5 5h5l2 2.2h8A1.5 1.5 0 0 1 21 8.7v9.8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/></svg>';
const ICON_ALL = '<svg class="ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3l9 5-9 5-9-5zM3 13l9 5 9-5"/></svg>';
const ICON_DOC = '<svg class="ico ico-doc" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></svg>';

/* ================= hiển thị một câu (dùng chung) ================= */
function questionView(q, editable) {
  const p = q.parts || {};
  let h = `<div class="qtext">${p.stem || ''}</div>`;
  const ans = q.answer || '';
  if (q.qtype === 'TN' && p.options) {
    h += '<div class="opts">' + p.options.map((o, i) => {
      const L = 'ABCD'[i], ok = ans === L, tag = editable ? 'button' : 'div';
      return `<${tag} class="opt ${ok ? 'ok' : ''}" data-opt="${L}" ${editable ? `title="Chọn ${L} là đáp án đúng"` : ''}><span class="L">${L}</span><span class="ot qtext">${o}</span>${ok ? '<span class="da">Đ.A</span>' : ''}</${tag}>`;
    }).join('') + '</div>';
    if (editable) h += `<div class="hint">Bấm vào phương án (hoặc phím A–D) để đặt làm đáp án đúng.</div>`;
  }
  if (q.qtype === 'ĐS' && p.items) {
    h += `<table class="ds-table"><thead><tr><th>Mệnh đề</th><th class="c">Đúng</th><th class="c">Sai</th></tr></thead><tbody>` +
      p.items.map((it, i) => {
        const v = ans[i];
        return `<tr><td class="qtext"><span class="il">${'abcd'[i]}</span>${it}</td>
          <td class="c"><button class="rad ${v === 'Đ' ? 'on' : ''}" data-ds="${i}" data-v="Đ" aria-label="Ý ${'abcd'[i]} đúng" ${editable ? '' : 'disabled'}></button></td>
          <td class="c"><button class="rad ${v === 'S' ? 'on' : ''}" data-ds="${i}" data-v="S" aria-label="Ý ${'abcd'[i]} sai" ${editable ? '' : 'disabled'}></button></td></tr>`;
      }).join('') + '</tbody></table>';
  }
  if (q.qtype === 'TLN') {
    h += `<div class="tln-row"><div class="tln"><span class="lbl">Đáp án:</span>` +
      (editable ? `<input class="tln-in" maxlength="6" value="${esc(ans)}" aria-label="Đáp án trả lời ngắn" placeholder="____">`
        : `<span class="boxes">${[0, 1, 2, 3].map(i => `<span class="box">${esc(ans[i] || '')}</span>`).join('')}</span>`) + `</div></div>`;
  }
  if (q.qtype !== 'TL' && (!ans || ans.includes('?')))
    h += `<div class="noans"><span class="chip bad">Chưa có đáp án${editable ? (q.qtype === 'TN' ? ' — bấm vào phương án đúng' : q.qtype === 'ĐS' ? ' — chọn Đúng/Sai cho từng ý' : ' — gõ vào ô đáp án') : ''}</span></div>`;
  if (p.solution) h += `<div class="sol"><div class="solh">Lời giải</div><div class="qtext">${p.solution}</div></div>`;
  return h;
}
function bindAnswer(root, q, onChange) {
  $$('[data-opt]', root).forEach(b => b.onclick = () => onChange(b.dataset.opt));
  $$('[data-ds]', root).forEach(b => b.onclick = () => {
    const n = (q.parts.items || []).length || 4;
    const arr = (q.answer || '').padEnd(n, '?').slice(0, n).split('');
    arr[+b.dataset.ds] = b.dataset.v;
    onChange(arr.join(''));
  });
  const inp = $('.tln-in', root);
  if (inp) inp.onchange = () => onChange(inp.value.trim());
}

/* ================= trạng thái ================= */
const S = {
  kind: store('kd_kind') || 'cd', trees: {}, cdFlat: [], sel: store('kd_sel') || {type: 'all'}, page: 1, size: 20, pages: 1,
  levels: new Set(), types: new Set(), noans: false, avoid: false, text: '', sort: store('kd_sort') || 'tree',
  view: store('kd_view') || 'grid', items: [], cart: new Set(store('kd_cart') || []), open: new Set(store('kd_open') || []),
};
function saveCart() { store('kd_cart', [...S.cart]); updateCart(); }
function setSel(sel) { S.sel = sel; store('kd_sel', sel); S.page = 1; }

/* ================= điều hướng ================= */
function showView() {
  const v = (location.hash || '#kho').slice(1);
  ['kho', 'nhap', 'taode'].forEach(n => { $('#view-' + n).hidden = n !== v; });
  $$('.tabs a').forEach(a => a.classList.toggle('on', a.dataset.view === v));
  if (v === 'taode') { refreshAvailability(); loadHistory(); updateCart(); }
}
window.addEventListener('hashchange', showView);

/* ================= cây thư mục ================= */
async function loadTrees() {
  const [cd, de] = await Promise.all([api('/api/folders?kind=cd'), api('/api/folders?kind=de')]);
  S.trees = {cd, de};
  $('#total-badge').innerHTML = `<b>${cd.total.toLocaleString('vi-VN')}</b> câu hỏi<br><b>${de.total}</b> đề thi trong kho`;
  S.cdFlat = []; S.deFlat = [];
  const walk = (arr, depth, out, path) => arr.forEach(n => { const p = path ? path + ' › ' + n.name : n.name; out.push({id: n.id, name: n.name, code: n.code, depth, path: p}); walk(n.children, depth + 1, out, p); });
  walk(cd.tree, 0, S.cdFlat, ''); walk(de.tree, 0, S.deFlat, '');
  renderTree(); fillAddCode();
}
const folderOptions = (cur, empty = '— chưa phân loại —') => `<option value="">${empty}</option>` +
  S.cdFlat.map(f => `<option value="${f.id}" ${String(f.id) === String(cur ?? '') ? 'selected' : ''}>${'\u2003'.repeat(f.depth)}${esc(f.name)}${f.code ? ' (' + esc(f.code) + ')' : ''}</option>`).join('');
const deFolderOptions = cur => S.deFlat.map(f => `<option value="${f.id}" ${String(f.id) === String(cur ?? '') ? 'selected' : ''}>${'\u2003'.repeat(f.depth)}${esc(f.name)}</option>`).join('');

function renderTree() {
  $('#tree-kind').value = S.kind;
  const T = S.trees[S.kind]; if (!T) return;
  const tq = norm($('#tree-q').value.trim());
  const isSel = (type, id) => S.sel.type === type && String(S.sel.id) === String(id) && S.sel.kind === S.kind;
  const selFolderPath = new Set();
  const markPath = (arr, trail) => arr.forEach(n => {
    const t2 = [...trail, n.id];
    if (isSel('folder', n.id) || (n.sets || []).some(s => isSel('set', s.id))) t2.forEach(x => selFolderPath.add(x));
    markPath(n.children, t2);
  });
  markPath(T.tree, []);
  const node = (n, depth) => {
    const sub = [];
    n.children.forEach(k => sub.push(...node(k, depth + 1)));
    (n.sets || []).forEach(s => { if (!tq || norm(s.title).includes(tq)) sub.push(setRow(s, depth + 1)); });
    const match = !tq || norm(n.name).includes(tq) || norm(n.code || '').includes(tq);
    if (!match && !sub.length) return [];
    const hasKids = n.children.length || (n.sets || []).length;
    const open = tq || S.open.has(n.id) || (selFolderPath.has(n.id) && !isSel('folder', n.id));
    const row = `<div class="tn d${Math.min(depth, 3)} ${isSel('folder', n.id) ? 'on' : ''}" style="--d:${depth}" data-fid="${n.id}" draggable="true" tabindex="0" role="treeitem" title="${esc(n.code || '')}">
      <span class="car">${hasKids ? (open ? '▾' : '▸') : ''}</span>${ICON_FOLDER}<span class="nm">${esc(n.name)}</span>
      <span class="ct">${n.count || 0}</span>
      <span class="acts"><span data-act="add" title="Thêm thư mục con">＋</span><span data-act="edit" title="Đổi tên / mã">✎</span><span data-act="up" title="Lên trên">↑</span><span data-act="down" title="Xuống dưới">↓</span><span data-act="del" title="Xoá thư mục">✕</span></span></div>`;
    return open || tq ? [row, ...sub] : [row];
  };
  const setRow = (s, depth) => `<div class="tn set ${isSel('set', s.id) ? 'on' : ''}" style="--d:${depth}" data-sid="${s.id}" draggable="true" tabindex="0" role="treeitem">
    <span class="car"></span>${ICON_DOC}<span class="nm">${esc(s.title)}</span><span class="ct">${s.n} câu</span></div>`;
  const rows = [];
  if (S.kind === 'cd') {
    rows.push(`<div class="tn d0 ${S.sel.type === 'all' && S.sel.kind === 'cd' ? 'on' : ''}" style="--d:0" data-root="1" tabindex="0"><span class="car"></span>${ICON_ALL}<span class="nm">Tất cả câu hỏi</span><span class="ct">${T.total}</span></div>`);
  } else {
    rows.push(`<div class="tn d0 ${S.sel.type === 'all' && S.sel.kind === 'de' ? 'on' : ''}" style="--d:0" data-root="1" tabindex="0"><span class="car"></span>${ICON_ALL}<span class="nm">Tất cả đề</span><span class="ct">${T.total} đề</span></div>`);
  }
  T.tree.forEach(n => rows.push(...node(n, 0)));
  if (S.kind === 'de') (T.loose || []).forEach(s => rows.push(setRow(s, 0)));
  if (S.kind === 'cd' && T.unclassified) rows.push(`<div class="tn d0 ${isSel('unclassified', 0) ? 'on' : ''}" style="--d:0" data-uncl="1" tabindex="0"><span class="car"></span>${ICON_FOLDER}<span class="nm">Chưa phân loại</span><span class="ct">${T.unclassified}</span></div>`);
  if (S.kind === 'de' && !T.total) rows.push('<div class="tree-empty">Chưa có đề nào. Vào Nhập liệu, chọn “Lưu thành đề thi”.</div>');
  $('#tree').innerHTML = rows.join('');
  bindTree();
}
function bindTree() {
  $$('#tree .tn').forEach(el => {
    el.onclick = async e => {
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (el.dataset.root) { setSel({type: 'all', kind: S.kind}); return afterSel(); }
      if (el.dataset.uncl) { setSel({type: 'unclassified', id: 0, kind: 'cd'}); return afterSel(); }
      if (el.dataset.sid) { setSel({type: 'set', id: +el.dataset.sid, kind: 'de'}); return afterSel(); }
      const fid = +el.dataset.fid;
      if (act) return folderAction(act, fid);
      const isOn = S.sel.type === 'folder' && S.sel.id === fid;
      if (isOn || e.target.classList.contains('car')) { S.open.has(fid) ? S.open.delete(fid) : S.open.add(fid); }
      else S.open.add(fid);
      store('kd_open', [...S.open]);
      setSel({type: 'folder', id: fid, kind: S.kind}); afterSel();
    };
    el.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', JSON.stringify(el.dataset.fid ? {fid: +el.dataset.fid} : {sid: +el.dataset.sid})); e.dataTransfer.effectAllowed = 'move'; });
    if (el.dataset.fid || el.dataset.root) {
      el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('drop-into'); });
      el.addEventListener('dragleave', () => el.classList.remove('drop-into'));
      el.addEventListener('drop', async e => {
        e.preventDefault(); el.classList.remove('drop-into');
        let d; try { d = JSON.parse(e.dataTransfer.getData('text/plain')); } catch (_) { return; }
        const target = el.dataset.root ? null : +el.dataset.fid;
        try {
          if (d.fid) { if (d.fid === target) return; await post('/api/folders/' + d.fid, {parent_id: target}, 'PATCH'); toast('Đã chuyển thư mục'); }
          else if (d.sid) { await post('/api/sets/' + d.sid, {folder_id: target}, 'PATCH'); toast('Đã chuyển đề'); }
          if (target) S.open.add(target);
          await loadTrees();
        } catch (err) { toast(err.message, 4000); }
      });
    }
  });
}
function afterSel() { renderTree(); refresh(); }

let FD = null;
function openFolderDlg(mode, fid) {
  const f = fid ? [...S.cdFlat, ...S.deFlat].find(x => x.id === fid) : null;
  FD = {mode, fid};
  $('#fd-title').textContent = mode === 'add' ? 'Thêm thư mục' : 'Đổi tên thư mục';
  $('#fd-where').textContent = mode === 'add' ? (f ? 'Bên trong: ' + f.path : 'Ở cấp ngoài cùng') : (f ? f.path : '');
  $('#fd-name').value = mode === 'edit' && f ? f.name : '';
  $('#fd-code').value = mode === 'edit' && f ? (f.code || '') : '';
  $('#fd-code-wrap').hidden = S.kind !== 'cd';
  $('#folder-dlg').showModal(); $('#fd-name').focus();
}
async function folderAction(act, fid) {
  if (act === 'add') return openFolderDlg('add', fid);
  if (act === 'edit') return openFolderDlg('edit', fid);
  if (act === 'up' || act === 'down') { await post(`/api/folders/${fid}/move`, {dir: act}); return loadTrees(); }
  if (act === 'del') {
    const f = [...S.cdFlat, ...S.deFlat].find(x => x.id === fid);
    if (!confirm(`Xoá thư mục “${f?.name}” và các thư mục con?\n\n${S.kind === 'cd' ? 'Các câu hỏi bên trong KHÔNG bị xoá, chúng được chuyển lên thư mục cha.' : 'Các đề bên trong KHÔNG bị xoá, chúng được chuyển lên thư mục cha.'}`)) return;
    const r = await api('/api/folders/' + fid, {method: 'DELETE'});
    toast(`Đã xoá thư mục${r.moved_questions ? ` · chuyển ${r.moved_questions} câu lên trên` : ''}${r.moved_sets ? ` · chuyển ${r.moved_sets} đề lên trên` : ''}`);
    if (S.sel.type === 'folder' && S.sel.id === fid) setSel({type: 'all', kind: S.kind});
    await loadTrees(); refresh();
  }
}
function setupTreeUI() {
  $('#tree-kind').onchange = e => { S.kind = e.target.value; store('kd_kind', S.kind); setSel({type: 'all', kind: S.kind}); $('#tree-q').value = ''; afterSel(); };
  let t; $('#tree-q').oninput = () => { clearTimeout(t); t = setTimeout(renderTree, 150); };
  $('#tree-add').onclick = () => openFolderDlg('add', S.sel.type === 'folder' && S.sel.kind === S.kind ? S.sel.id : null);
  $('#fd-save').onclick = async e => {
    e.preventDefault();
    const name = $('#fd-name').value.trim(); if (!name) return toast('Chưa nhập tên');
    try {
      if (FD.mode === 'add') {
        const r = await post('/api/folders', {kind: S.kind, parent_id: FD.fid, name, code: $('#fd-code').value.trim()});
        if (FD.fid) S.open.add(FD.fid);
        toast(r.code ? `Đã thêm · mã ${r.code}` : 'Đã thêm thư mục');
      } else {
        const body = {name}; if (S.kind === 'cd') body.code = $('#fd-code').value.trim();
        await post('/api/folders/' + FD.fid, body, 'PATCH'); toast('Đã lưu');
      }
      $('#folder-dlg').close(); await loadTrees();
    } catch (err) { toast(err.message, 4000); }
  };
}

/* ================= danh sách + thống kê ================= */
function selParams(p) {
  const s = S.sel;
  if (s.kind === 'de' || S.kind === 'de') p.set('scope', 'de');
  if (s.type === 'folder') p.set('folder', s.id);
  if (s.type === 'set') p.set('set', s.id);
  if (s.type === 'unclassified') p.set('unclassified', 1);
  if (S.text) p.set('q', S.text);
  if (S.avoid) p.set('avoid_days', 30);
  return p;
}
function listParams() {
  const p = selParams(new URLSearchParams({page: S.page, size: S.size, sort: S.sort}));
  if (S.levels.size) p.set('level', [...S.levels].join(','));
  if (S.types.size) p.set('qtype', [...S.types].join(','));
  if (S.noans) p.set('no_answer', 1);
  return p;
}
function refresh() { loadList(); loadStats(); renderSetBar(); }
let listSeq = 0;
async function loadList() {
  const seq = ++listSeq;
  const d = await api('/api/questions?' + listParams());
  if (seq !== listSeq) return;
  S.items = d.items; S.pages = Math.max(1, Math.ceil(d.total / d.size));
  $('#pg-cur').textContent = S.page; $('#pg-all').textContent = S.pages;
  $('#pg-prev').disabled = S.page <= 1; $('#pg-next').disabled = S.page >= S.pages;
  renderGrid(); renderPager();
}
function qLabel(q, i) {
  if ((S.sel.type === 'set' || S.kind === 'de') && q.set_id) return `${q.set_part ? 'P.' + ROMAN[q.set_part] + ' · ' : ''}Câu ${q.part_no}`;
  return `Câu ${(S.page - 1) * S.size + i + 1}`;
}
function renderGrid() {
  const el = $('#qgrid');
  el.classList.toggle('list', S.view === 'list');
  $$('.viewsw button').forEach(b => b.classList.toggle('on', b.dataset.v === S.view));
  if (!S.items.length) {
    const T = S.trees.cd;
    el.innerHTML = `<div class="empty">${T && T.total ? 'Không có câu hỏi phù hợp.' : 'Kho đang trống. Vào <a href="#nhap">Nhập liệu</a> để đưa file Word vào.'}</div>`;
    return updateSelPage();
  }
  el.innerHTML = S.items.map((q, i) => {
    const picked = S.cart.has(q.id);
    const noans = q.qtype !== 'TL' && (!q.answer || q.answer.includes('?'));
    return `<article class="qc ${picked ? 'picked' : ''}" data-i="${i}">
      <div class="qc-h"><span class="no">${qLabel(q, i)}</span><span class="badge">${TYPE_NAME[q.qtype]}</span>
        ${lvButtons(q.level, true)}
        <button class="add ${picked ? 'on' : ''}" aria-label="Chọn câu này">THÊM <span class="circ"></span></button></div>
      <div class="qc-b"><div class="meta"><span class="tag">${esc(q.code || 'chưa phân loại')}</span>
        ${noans ? '<span class="chip bad">chưa có đáp án</span>' : ''}${q.has_solution ? '' : '<span class="chip warn">chưa có lời giải</span>'}
        <span class="used">${q.used ? 'đã dùng ' + q.used + ' lần' : ''}</span></div>
        <div class="qtext">${q.stem}</div></div></article>`;
  }).join('');
  renderMath(el);
  $$('.qc', el).forEach(card => {
    const i = +card.dataset.i, q = S.items[i];
    card.onclick = () => openDetail(i);
    $$('.lvset button', card).forEach(b => b.onclick = e => { e.stopPropagation(); setLevel(q, b.dataset.lv); });
    $('.add', card).onclick = e => { e.stopPropagation(); togglePick(q.id); };
  });
  updateSelPage();
}
function renderPager() {
  let ph = '';
  if (S.pages > 1) {
    const from = Math.max(1, S.page - 3), to = Math.min(S.pages, S.page + 3);
    if (S.page > 1) ph += `<button class="btn sm" data-p="${S.page - 1}">‹ Trước</button>`;
    for (let i = from; i <= to; i++) ph += `<button class="btn sm ${i === S.page ? 'maroon' : ''}" data-p="${i}">${i}</button>`;
    if (S.page < S.pages) ph += `<button class="btn sm" data-p="${S.page + 1}">Sau ›</button>`;
  }
  $('#pager').innerHTML = ph;
  $$('#pager button').forEach(b => b.onclick = () => gotoPage(+b.dataset.p));
}
function gotoPage(p) { S.page = Math.min(Math.max(1, p), S.pages); loadList(); window.scrollTo(0, 0); }
async function loadStats() {
  const s = await api('/api/stats?' + selParams(new URLSearchParams()));
  $('#stats').innerHTML = `<div class="st-h">Thống kê</div>
    <div class="st-group"><span class="k label">Mức</span>
      ${LEVELS.map(([k], i) => `<span class="k ${S.levels.has(k) ? 'on' : ''}" data-lv="${k}" data-n="${s.level[k] || 0}" title="Lọc ${LV_NAME[k]}" role="button" tabindex="0">Mức ${i + 1}</span>`).join('')}</div>
    <div class="st-sep"></div>
    <div class="st-group"><span class="k label">Dạng</span>
      ${TYPES.map(([k, n]) => `<span class="k ${S.types.has(k) ? 'on' : ''}" data-ty="${k}" data-n="${s.type[k] || 0}" title="Lọc ${n}" role="button" tabindex="0">${n}</span>`).join('')}</div>
    ${s.no_answer ? `<div class="st-group"><span class="k ${S.noans ? 'on' : ''}" data-noans="1" data-n="${s.no_answer}" title="Lọc câu chưa có đáp án" role="button" tabindex="0">Chưa có đáp án</span></div>` : ''}
    <div class="st-total">Tổng<b>${s.total.toLocaleString('vi-VN')}</b></div>`;
  $$('#stats [data-lv]').forEach(b => b.onclick = () => { toggle(S.levels, b.dataset.lv); filtersChanged(); });
  $$('#stats [data-ty]').forEach(b => b.onclick = () => { toggle(S.types, b.dataset.ty); filtersChanged(); });
  $$('#stats [data-noans]').forEach(b => b.onclick = () => { S.noans = !S.noans; $('#f-noans').checked = S.noans; filtersChanged(); });
}
async function renderSetBar() {
  const bar = $('#setbar');
  if (S.sel.type !== 'set') { bar.hidden = true; return; }
  let s; try { s = await api('/api/sets/' + S.sel.id); } catch (_) { bar.hidden = true; return; }
  const cnt = TYPES.filter(([k]) => s.counts[k]).map(([k, n]) => `${n} ${s.counts[k]}`).join(' · ');
  bar.innerHTML = `<div class="grow"><div class="t">${esc(s.title)}</div><div class="p">${esc(s.folder_path || 'Chưa xếp thư mục')} · ${cnt} · nhập ngày ${s.created}</div></div>
    <div class="acts"><button class="btn" data-sa="docx0">Tải đề (.docx)</button><button class="btn" data-sa="docx1">Tải kèm lời giải</button>
    <button class="btn" data-sa="pick">Chọn cả đề</button><button class="btn" data-sa="rename">Đổi tên</button><button class="btn danger" data-sa="del">Xoá đề</button></div>`;
  bar.hidden = false;
  $$('[data-sa]', bar).forEach(b => b.onclick = async () => {
    const a = b.dataset.sa;
    try {
      if (a.startsWith('docx')) await download(`/api/sets/${s.id}/docx?solution=${a === 'docx1' ? 1 : 0}`, null, 'de.docx');
      if (a === 'pick') { const all = await api(`/api/questions?set=${s.id}&scope=de&size=500`); all.items.forEach(q => S.cart.add(q.id)); saveCart(); renderGrid(); toast(`Đã chọn ${all.items.length} câu`); }
      if (a === 'rename') { const t = prompt('Tên đề:', s.title); if (t && t.trim()) { await post('/api/sets/' + s.id, {title: t.trim()}, 'PATCH'); await loadTrees(); renderSetBar(); } }
      if (a === 'del') {
        if (!confirm(`Xoá đề “${s.title}”?`)) return;
        const keep = confirm('Giữ lại các câu hỏi của đề này trong kho chuyên đề?\n\nOK = giữ lại câu hỏi · Huỷ = xoá luôn câu hỏi');
        await api(`/api/sets/${s.id}?with_questions=${keep ? 0 : 1}`, {method: 'DELETE'});
        setSel({type: 'all', kind: 'de'}); await loadTrees(); refresh(); toast('Đã xoá đề');
      }
    } catch (e) { toast(e.message, 4000); }
  });
}
function toggle(set, k) { set.has(k) ? set.delete(k) : set.add(k); }
function renderFilterPop() {
  $('#f-level').innerHTML = LEVELS.map(([k, n], i) => `<button data-k="${k}" class="${S.levels.has(k) ? 'on' : ''}">Mức ${i + 1} · ${n}</button>`).join('');
  $('#f-type').innerHTML = TYPES.map(([k, n]) => `<button data-k="${k}" class="${S.types.has(k) ? 'on' : ''}">${n}</button>`).join('');
  $$('#f-level button').forEach(b => b.onclick = () => { toggle(S.levels, b.dataset.k); filtersChanged(); });
  $$('#f-type button').forEach(b => b.onclick = () => { toggle(S.types, b.dataset.k); filtersChanged(); });
  const n = S.levels.size + S.types.size + (S.noans ? 1 : 0) + (S.avoid ? 1 : 0);
  $('#filter-n').hidden = !n; $('#filter-n').textContent = n;
}
function filtersChanged() { S.page = 1; renderFilterPop(); loadList(); loadStats(); }
async function setLevel(q, lv) {
  const nv = q.level === lv ? '' : lv;
  await post('/api/questions/' + q.id, {level: nv}, 'PATCH');
  q.level = nv; renderGrid(); loadStats();
  return nv;
}
function togglePick(id) { S.cart.has(id) ? S.cart.delete(id) : S.cart.add(id); saveCart(); renderGrid(); }
function updateSelPage() {
  const all = S.items.length && S.items.every(q => S.cart.has(q.id));
  $('#sel-page-txt').textContent = all ? 'Bỏ chọn cả trang' : `Chọn cả trang (${S.items.length})`;
}

/* ================= hộp chi tiết ================= */
let D = {i: 0, q: null};
async function openDetail(i) {
  D.i = i;
  const q = await api('/api/questions/' + S.items[i].id);
  D.q = q;
  $('#qd-head').innerHTML = `<span class="no">${qLabel(S.items[i], i)}</span><span class="badge">${TYPE_NAME[q.qtype]}</span>
    <span class="cid">[${esc(q.code || 'chưa phân loại')}] ID: ${q.id}</span><button class="copy" id="qd-copy" title="Sao chép mã" aria-label="Sao chép mã">⧉</button>
    ${lvButtons(q.level)}<button class="x" id="qd-x" aria-label="Đóng">✕</button>`;
  const warns = q.warnings.filter(w => !/^(Chưa có (chuyên đề|mức độ|đáp án))|chưa có trong cây/.test(w));
  $('#qd-body').innerHTML = `<span class="tag">${esc(q.folder_path)}</span>` + questionView(q, true) +
    (warns.length ? `<div class="warns">${warns.map(w => `<span class="chip warn">${esc(w)}</span>`).join('')}</div>` : '') +
    `<div class="hint">${q.set ? 'Thuộc đề: ' + esc(q.set.title) + ' · ' : ''}Nguồn: ${esc(q.source || '—')} · ${q.uses.length ? 'Đã dùng ' + q.uses.length + ' lần, gần nhất: ' + esc(q.uses[0].exam) + ' (' + q.uses[0].at + ')' : 'Chưa dùng trong đề nào'}</div>`;
  renderMath($('#qd-body'));
  bindAnswer($('#qd-body'), q, a => saveAnswer(q, a));
  $$('#qd-head .lvset button').forEach(b => b.onclick = async () => { const nv = await setLevel(S.items[D.i], b.dataset.lv); $$('#qd-head .lvset button').forEach(x => x.classList.toggle('on', x.dataset.lv === nv)); });
  $('#qd-x').onclick = () => $('#qdlg').close();
  $('#qd-copy').onclick = () => { navigator.clipboard?.writeText(q.code || String(q.id)); toast('Đã sao chép mã'); };
  $('#qd-docx').onclick = () => download(`/api/questions/${q.id}/docx`, null, 'cau.docx').catch(err => toast(err.message));
  $('#qd-pick').checked = S.cart.has(q.id);
  $('#qd-prev').disabled = D.i === 0 && S.page === 1;
  $('#qd-next').disabled = D.i === S.items.length - 1 && S.page >= S.pages;
  if (!$('#qdlg').open) $('#qdlg').showModal();
  $('#qd-body').scrollTop = 0;
}
async function saveAnswer(q, a) {
  try {
    await post('/api/questions/' + q.id, {answer: a}, 'PATCH');
    S.items[D.i].answer = a;
    toast(q.qtype === 'TN' ? `Đã đặt đáp án ${a}` : 'Đã lưu đáp án');
    openDetail(D.i); renderGrid(); loadStats();
  } catch (e) { toast(e.message); }
}
async function moveDetail(step) {
  let i = D.i + step;
  if (i < 0) { if (S.page <= 1) return; S.page--; await loadList(); i = S.items.length - 1; }
  else if (i >= S.items.length) { if (S.page >= S.pages) return; S.page++; await loadList(); i = 0; }
  openDetail(i);
}
function setupDetail() {
  $('#qd-prev').onclick = () => moveDetail(-1);
  $('#qd-next').onclick = () => moveDetail(1);
  $('#qd-pick').onchange = () => togglePick(D.q.id);
  $('#qd-del').onclick = async () => {
    if (!confirm('Xoá hẳn câu này khỏi kho?')) return;
    await api('/api/questions/' + D.q.id, {method: 'DELETE'});
    S.cart.delete(D.q.id); saveCart(); $('#qdlg').close(); await loadTrees(); refresh(); toast('Đã xoá câu hỏi');
  };
  $('#qd-edit').onclick = () => { $('#c-code').innerHTML = folderOptions(D.q.folder_id); $('#code-dlg').showModal(); };
  $('#c-save').onclick = async () => {
    await post('/api/questions/' + D.q.id, {folder_id: +$('#c-code').value || null}, 'PATCH');
    toast('Đã xếp vào chuyên đề'); await loadTrees(); await loadList(); if (S.items.length) openDetail(Math.min(D.i, S.items.length - 1)); else $('#qdlg').close();
  };
  $('#qdlg').addEventListener('keydown', e => {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
    if (e.key === 'ArrowRight') moveDetail(1);
    else if (e.key === 'ArrowLeft') moveDetail(-1);
    else if (/^[1-4]$/.test(e.key)) $(`#qd-head .lvset button[data-lv="M${e.key}"]`)?.click();
    else if (D.q?.qtype === 'TN' && /^[a-dA-D]$/.test(e.key)) saveAnswer(D.q, e.key.toUpperCase());
    else return;
    e.preventDefault();
  });
}

/* ================= câu đã chọn ================= */
let cartInfo = {};
async function updateCart() {
  $$('.cart-n').forEach(x => x.textContent = S.cart.size);
  $('#cartbar').hidden = S.cart.size === 0;
  for (const id of [...S.cart].filter(id => !cartInfo[id])) {
    try { const q = await api('/api/questions/' + id); cartInfo[id] = {level: q.level, qtype: q.qtype}; } catch (_) { S.cart.delete(id); }
  }
  const byType = {}, byLv = {};
  [...S.cart].forEach(id => { const c = cartInfo[id]; if (!c) return; byType[c.qtype] = (byType[c.qtype] || 0) + 1; byLv[c.level] = (byLv[c.level] || 0) + 1; });
  $('#cart-chips').innerHTML = TYPES.map(([k, n]) => byType[k] ? `<span>${n}: ${byType[k]}</span>` : '').join('') +
    LEVELS.map(([k], i) => byLv[k] ? `<span>Mức ${i + 1}: ${byLv[k]}</span>` : '').join('');
  $('#cart-summary').innerHTML = TYPES.map(([k, n]) => `<span class="chip">${n}: ${byType[k] || 0} câu</span>`).join('');
}

/* ================= nhập liệu ================= */
let IMP = null;
async function convertMathType(file) {
  const fd = new FormData(); fd.append('file', file);
  const st = $('#mt-status'); st.textContent = `Đang đổi ${file.name}…`;
  let r;
  try { r = await fetch('/api/tools/mathtype', {method: 'POST', body: fd}); } catch (_) { st.textContent = OFFLINE; return; }
  if (!r.ok) { const j = await r.json().catch(() => ({})); st.innerHTML = `<span class="err">${esc(j.detail || r.statusText)}</span>`; return; }
  const n = r.headers.get('X-Converted'), bad = +r.headers.get('X-Failed');
  const blob = await r.blob();
  const name = file.name.replace(/\.docx$/i, '') + ' (Equation).docx';
  if (DESK()) {
    const b64 = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result.split(',')[1]); fr.readAsDataURL(blob); });
    const s = await window.pywebview.api.save_bytes(b64, name);
    if (s.ok) savedToast(s.path);
  } else {
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }
  st.innerHTML = `<b>${esc(file.name)}</b>: đã đổi ${n} công thức${bad ? `, ${bad} công thức không đổi được (giữ MathType)` : ''}.`;
}
function setupImport() {
  $('#mt-pick').onclick = () => $('#mt-input').click();
  $('#mt-input').onchange = async e => { for (const f of e.target.files) await convertMathType(f); e.target.value = ''; };
  const drop = $('#drop'), inp = $('#file-input');
  drop.onclick = e => { if (e.target.tagName !== 'A') inp.click(); };
  $('#pick').onclick = e => { e.stopPropagation(); inp.click(); };
  inp.onchange = () => { if (inp.files.length) doPreview(inp.files); inp.value = ''; };
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', e => { if (e.dataTransfer.files.length) doPreview(e.dataTransfer.files); });
}
async function doPreview(files) {
  const fd = new FormData();
  [...files].forEach(f => fd.append('files', f));
  $('#import-result').innerHTML = '<div class="imp"><div class="imp-head">Đang đọc file…</div></div>';
  try { IMP = await api('/api/import/preview', {method: 'POST', body: fd}); }
  catch (e) { $('#import-result').innerHTML = `<div class="err">${esc(e.message)}</div>`; return; }
  IMP.edits = {}; IMP.skip = new Set(); IMP.focus = null;
  IMP.all = IMP.files.flatMap(f => f.questions || []);
  const lastMode = store('kd_impmode') || {};
  IMP.asExam = lastMode.asExam ?? IMP.all.length >= 10;
  IMP.examFolder = lastMode.folder || S.deFlat[0]?.id;
  IMP.titles = Object.fromEntries(IMP.files.map(f => [f.file, f.title || f.file]));
  IMP.all.forEach(q => { if (q.duplicate && !IMP.asExam) IMP.skip.add(q.idx); });
  renderImport();
}
const impVal = (q, k) => (IMP.edits[q.idx] && k in IMP.edits[q.idx]) ? IMP.edits[q.idx][k] : q[k];
function impEdit(q, k, v) { (IMP.edits[q.idx] = IMP.edits[q.idx] || {})[k] = v; }
function renderImport() {
  const all = IMP.all;
  const noAns = all.filter(q => q.qtype !== 'TL' && !(impVal(q, 'answer') || '').replace(/\?/g, '')).length;
  const noCode = all.filter(q => !impVal(q, 'folder_id')).length, noLv = all.filter(q => !impVal(q, 'level')).length;
  const nDup = all.filter(q => q.duplicate).length, nSol = all.filter(q => q.parts.solution).length;
  let h = `<div class="imp"><div class="imp-head"><div class="grow"><b>Đã đọc ${all.length} câu</b> từ ${IMP.files.length} file</div>
      <span class="chip">${nSol}/${all.length} có lời giải</span>
      <span class="chip ${noAns ? 'bad' : ''}">${noAns ? noAns + ' câu chưa có đáp án' : 'Đủ đáp án'}</span>
      ${noCode ? `<span class="chip warn">${noCode} câu chưa có chuyên đề</span>` : ''}${noLv ? `<span class="chip warn">${noLv} câu chưa có mức</span>` : ''}
      ${nDup ? `<span class="chip dup">${nDup} câu đã có trong kho</span>` : ''}</div>
    <div class="imp-mode">
      <label class="radio"><input type="radio" name="impmode" value="0" ${IMP.asExam ? '' : 'checked'}> Chỉ đưa câu hỏi vào kho chuyên đề</label>
      <label class="radio"><input type="radio" name="impmode" value="1" ${IMP.asExam ? 'checked' : ''}> Lưu mỗi file thành một đề trong <b>Tổng hợp đề thi</b></label>
      ${IMP.asExam ? `<span class="exam-opts">vào thư mục <select id="imp-exfolder">${deFolderOptions(IMP.examFolder)}</select></span>` : ''}
    </div>
    <div class="imp-tools"><b class="small">Xếp các câu chưa có chuyên đề vào:</b><select class="bulk-code">${folderOptions('', '— chọn chuyên đề —')}</select><button class="btn sm" id="bulk-apply">Xếp</button>
      <span class="muted small">· Bấm vào một câu rồi dùng phím 1–4 chọn mức, A–D chọn đáp án, ↑ ↓ chuyển câu.</span></div>`;
  IMP.files.forEach(f => {
    h += `<div class="imp-file">${esc(f.file)}${IMP.asExam && !f.error ? ` <input class="title" data-file="${esc(f.file)}" value="${esc(IMP.titles[f.file])}" aria-label="Tên đề">` : ''}</div>`;
    if (f.error) { h += `<div class="imp-q"><div class="err">${esc(f.error)}</div></div>`; return; }
    (f.warnings || []).forEach(w => { h += `<div class="imp-q"><div class="${(w.startsWith('Đã tự đổi') || w.startsWith('Đã đọc bảng')) && !w.includes('chưa có trong cây') ? 'okmsg' : 'err'}">${esc(w)}</div></div>`; });
    f.questions.forEach(q => {
      const view = {qtype: q.qtype, answer: impVal(q, 'answer'), parts: q.parts};
      const lv = impVal(q, 'level'), fid = impVal(q, 'folder_id');
      const warns = q.warnings.filter(w => !/^Chưa có (chuyên đề|mức độ|đáp án)/.test(w));
      h += `<div class="imp-q ${IMP.skip.has(q.idx) ? 'skip' : ''} ${IMP.focus === q.idx ? 'focus' : ''}" data-idx="${q.idx}">
        <div><div class="qhead"><span class="tag">${q.part ? 'Phần ' + ROMAN[q.part] + ' · ' : ''}Câu ${q.num ?? q.no}</span><span class="badge">${TYPE_NAME[q.qtype]}</span></div>
          ${questionView(view, true)}${warns.length ? `<div class="warns">${warns.map(w => `<span class="chip warn">${esc(w)}</span>`).join('')}</div>` : ''}</div>
        <div class="imp-side">
          <label class="check"><input type="checkbox" class="inc" ${IMP.skip.has(q.idx) ? '' : 'checked'}> Lưu câu này</label>
          ${q.duplicate ? '<span class="chip dup">Câu này đã có trong kho</span>' : ''}
          <b class="small">Chuyên đề</b><select class="code" aria-label="Chuyên đề">${folderOptions(fid, '— chọn chuyên đề —')}</select>
          <b class="small">Mức độ</b><div class="lvbtns">${LEVELS.map(([k, n], i) => `<button class="${k === lv ? 'on' : ''}" data-lv="${k}" title="${n} (phím ${i + 1})">Mức ${i + 1}</button>`).join('')}</div>
        </div></div>`;
    });
  });
  const n = all.filter(q => !IMP.skip.has(q.idx)).length;
  h += `<div class="sticky-save"><b>${n} câu sẽ được lưu${IMP.asExam ? ` · ${IMP.files.filter(f => !f.error).length} đề` : ''}</b><span class="small grow" style="opacity:.8">Câu thiếu chuyên đề, mức hay đáp án vẫn lưu được, sửa sau trong Kho.</span>
        <button class="btn ghost-light" id="imp-cancel">Huỷ</button><button class="btn amber" id="imp-save" ${n ? '' : 'disabled'}>Lưu vào kho</button></div></div>`;
  const keepY = window.scrollY;
  $('#import-result').innerHTML = h;
  window.scrollTo(0, keepY);
  renderMath($('#import-result'));
  $$('input[name=impmode]').forEach(r => r.onchange = () => { IMP.asExam = r.value === '1'; store('kd_impmode', {asExam: IMP.asExam, folder: IMP.examFolder}); renderImport(); });
  $('#imp-exfolder') && ($('#imp-exfolder').onchange = e => { IMP.examFolder = +e.target.value; store('kd_impmode', {asExam: IMP.asExam, folder: IMP.examFolder}); });
  $$('.imp-file input.title').forEach(i => i.oninput = () => { IMP.titles[i.dataset.file] = i.value; });
  $$('.imp-q[data-idx]').forEach(row => {
    const q = IMP.all.find(x => x.idx === +row.dataset.idx);
    row.addEventListener('click', () => { if (IMP.focus !== q.idx) { IMP.focus = q.idx; $$('.imp-q').forEach(r => r.classList.toggle('focus', r === row)); } });
    $('.inc', row).onchange = e => { e.target.checked ? IMP.skip.delete(q.idx) : IMP.skip.add(q.idx); renderImport(); };
    $('.code', row).onchange = e => { impEdit(q, 'folder_id', +e.target.value || null); renderImport(); };
    $$('.lvbtns button', row).forEach(b => b.onclick = () => { impEdit(q, 'level', b.dataset.lv); IMP.focus = q.idx; renderImport(); });
    bindAnswer(row, {qtype: q.qtype, answer: impVal(q, 'answer'), parts: q.parts}, a => { impEdit(q, 'answer', a); IMP.focus = q.idx; renderImport(); });
  });
  $('#bulk-apply').onclick = () => {
    const c = +$('.bulk-code').value; if (!c) return toast('Chọn chuyên đề trước');
    let k = 0; IMP.all.forEach(q => { if (!impVal(q, 'folder_id')) { impEdit(q, 'folder_id', c); k++; } });
    toast(`Đã xếp ${k} câu`); renderImport();
  };
  $('#imp-cancel').onclick = () => { IMP = null; $('#import-result').innerHTML = ''; };
  $('#imp-save').onclick = async () => {
    try {
      const body = {token: IMP.token, edits: IMP.edits, skip: [...IMP.skip], keep_duplicates: true};
      if (IMP.asExam) body.as_exam = {enabled: true, folder_id: IMP.examFolder, titles: IMP.titles};
      const r = await post('/api/import/commit', body);
      $('#import-result').innerHTML = `<div class="imp"><div class="imp-head"><b>Đã lưu ${r.saved} câu${r.sets.length ? ` · ${r.sets.length} đề vào Tổng hợp đề thi` : ''}.</b> <a href="#kho" style="color:var(--amber)">Xem trong Kho câu hỏi →</a></div></div>`;
      if (r.sets.length) { S.kind = 'de'; store('kd_kind', 'de'); setSel({type: 'set', id: r.sets[0], kind: 'de'}); S.open.add(IMP.examFolder); }
      IMP = null; await loadTrees(); refresh();
    } catch (e) { toast(e.message, 5000); }
  };
}
document.addEventListener('keydown', e => {
  if (!IMP || $('#view-nhap').hidden || IMP.focus === null) return;
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
  const order = IMP.all.map(q => q.idx), pos = order.indexOf(IMP.focus), q = IMP.all[pos];
  if (/^[1-4]$/.test(e.key)) impEdit(q, 'level', 'M' + e.key);
  else if (q.qtype === 'TN' && /^[a-dA-D]$/.test(e.key)) impEdit(q, 'answer', e.key.toUpperCase());
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') IMP.focus = order[Math.max(0, Math.min(order.length - 1, pos + (e.key === 'ArrowDown' ? 1 : -1)))];
  else return;
  e.preventDefault(); renderImport();
  $('.imp-q.focus')?.scrollIntoView({block: 'center', behavior: 'smooth'});
});

/* ================= tạo đề ================= */
let MX = store('kd_matrix2') || {TN: [], 'ĐS': [], TLN: [], TL: []};
let curPart = 'TN', mode = 'matrix', avail = null;
function saveMx() { store('kd_matrix2', MX); }
function fillAddCode() {
  $('#add-code').innerHTML = `<option value="">Toàn bộ kho</option>` +
    S.cdFlat.map(f => `<option value="${f.id}">${'\u2003'.repeat(f.depth)}${esc(f.name)}</option>`).join('');
}
const folderName = id => id ? (S.cdFlat.find(f => f.id === id)?.path || '(thư mục đã xoá)') : 'Toàn bộ kho';
function partTotal(t) { return MX[t].reduce((s, r) => s + MXCOLS.reduce((a, [k]) => a + (+r[k] || 0), 0), 0); }
function renderMatrix() {
  $('#part-tabs').innerHTML = TYPES.map(([k, n], i) =>
    `<button data-p="${k}" class="${k === curPart ? 'on' : ''}"><span class="pn">Phần ${ROMAN[i + 1]} · ${n}</span><span class="ps">${partTotal(k)} câu</span></button>`).join('');
  $$('#part-tabs button').forEach(b => b.onclick = () => { curPart = b.dataset.p; renderMatrix(); });
  const rows = MX[curPart], ai = TYPES.findIndex(([k]) => k === curPart);
  let h = `<thead><tr><th>Chuyên đề</th>${MXCOLS.map(([k, n], i) => `<th><span class="lvh">${k === 'ANY' ? 'Bất kỳ' : 'Mức ' + (i + 1)}</span><div class="small muted" style="font-weight:500">${k === 'ANY' ? 'cả câu chưa phân mức' : n}</div></th>`).join('')}<th>Tổng</th><th></th></tr></thead><tbody>`;
  rows.forEach((r, i) => {
    const av = avail && avail[ai] && avail[ai][i];
    const path = folderName(r.folder).split(' › ');
    h += `<tr><td>${esc(path[path.length - 1])}<div class="small muted" style="font-weight:400">${esc(path.slice(0, -1).join(' › '))}</div></td>` +
      MXCOLS.map(([k]) => {
        const a = av ? av[k] : null, bad = a !== null && (+r[k] || 0) > a;
        return `<td><input type="number" min="0" value="${r[k] || ''}" data-i="${i}" data-k="${k}" aria-label="${k}"><span class="avail ${bad ? 'bad' : ''}">${a === null ? '' : 'còn ' + a}</span></td>`;
      }).join('') +
      `<td>${MXCOLS.reduce((a, [k]) => a + (+r[k] || 0), 0)}</td><td><button class="rm" data-rm="${i}" aria-label="Xoá dòng">×</button></td></tr>`;
  });
  if (!rows.length) h += `<tr><td colspan="8" class="muted" style="text-align:center;padding:18px">Chưa có dòng nào. Chọn chuyên đề bên dưới rồi bấm “Thêm dòng”.</td></tr>`;
  const sums = MXCOLS.map(([k]) => rows.reduce((a, r) => a + (+r[k] || 0), 0));
  h += `</tbody><tfoot><tr><td>Tổng phần này</td>${sums.map(s => `<td>${s}</td>`).join('')}<td style="color:var(--bad)">${partTotal(curPart)}</td><td></td></tr></tfoot>`;
  $('#matrix').innerHTML = h;
  $$('#matrix input').forEach(inp => inp.onchange = () => {
    MX[curPart][+inp.dataset.i][inp.dataset.k] = Math.max(0, +inp.value || 0); saveMx(); renderMatrix(); refreshAvailability();
  });
  $$('#matrix [data-rm]').forEach(b => b.onclick = () => { MX[curPart].splice(+b.dataset.rm, 1); saveMx(); renderMatrix(); refreshAvailability(); });
  $('#exam-summary').innerHTML = TYPES.map(([k, n]) => `<span class="chip">${n}: ${partTotal(k)} câu</span>`).join('') +
    `<span class="chip" style="background:var(--amber-soft);border-color:var(--amber)">Tổng: ${TYPES.reduce((a, [k]) => a + partTotal(k), 0)} câu</span>`;
}
let avTimer;
function refreshAvailability() {
  clearTimeout(avTimer);
  avTimer = setTimeout(async () => {
    const body = {avoid_days: $('#e-avoid').checked ? 30 : 0, need_solution: $('#e-needsol').checked,
      parts: TYPES.map(([k]) => ({qtype: k, rows: MX[k].map(r => ({folder: r.folder}))}))};
    try { avail = (await post('/api/exam/availability', body)).parts; renderMatrix(); } catch (_) {}
  }, 200);
}
function examBody(extra = {}) {
  const b = {
    title: $('#e-title').value, grade: $('#e-grade').value, minutes: +$('#e-minutes').value,
    n_codes: +$('#e-ncodes').value, start_code: +$('#e-start').value,
    shuffle_q: $('#e-shq').checked, shuffle_opt: $('#e-sho').checked,
    avoid_days: $('#e-avoid').checked ? 30 : 0, need_solution: $('#e-needsol').checked, with_solution: $('#e-withsol').checked, ...extra};
  if (mode === 'cart') b.cart_ids = [...S.cart];
  else b.parts = TYPES.map(([k]) => ({qtype: k, rows: MX[k]}));
  return b;
}
async function generate(extra) {
  const btn = $('#gen-btn'); btn.disabled = true; $('#gen-msg').textContent = 'Đang ghép đề…';
  try {
    const r = await download('/api/exam/generate', examBody(extra), 'de.zip');
    $('#gen-msg').textContent = r ? `Đã tạo xong: ${r.name} (các mã đề, đáp án${$('#e-withsol').checked ? ', lời giải' : ''}).` : 'Đã tạo đề (chưa lưu file — tải lại ở mục “Đề đã tạo”).';
    loadHistory(); refreshAvailability();
  } catch (e) {
    if (e.status === 409 && e.body && e.body.short) {
      $('#gen-msg').textContent = '';
      if (confirm('Kho không đủ câu:\n\n• ' + e.body.short.join('\n• ') + '\n\nVẫn tạo đề với số câu hiện có?')) { btn.disabled = false; return generate({...extra, allow_short: true}); }
    } else $('#gen-msg').innerHTML = `<span class="err">${esc(e.message)}</span>`;
  }
  finally { btn.disabled = false; }
}
async function loadHistory() {
  const h = await api('/api/exams');
  $('#exam-history').innerHTML = h.length ? h.map(e => `<a href="#" data-dl="/api/exams/${e.id}/zip"><span>${esc(e.title)}<br><span class="muted small">${e.at} · ${e.n} câu</span></span><span>⬇</span></a>`).join('')
    : '<span class="muted small">Chưa tạo đề nào.</span>';
  $$('#exam-history [data-dl]').forEach(a => a.onclick = e => { e.preventDefault(); download(a.dataset.dl, null, 'de.zip').catch(err => toast(err.message)); });
}
function setMode(m) {
  mode = m; $$('.mode').forEach(x => x.classList.toggle('on', x.dataset.mode === m));
  $('#mode-matrix').hidden = m !== 'matrix'; $('#mode-cart').hidden = m !== 'cart';
}
function setupExam() {
  $('#add-row-btn').onclick = () => {
    const folder = +$('#add-code').value || null;
    if (MX[curPart].some(r => r.folder === folder)) return toast('Chuyên đề này đã có trong bảng');
    MX[curPart].push({folder}); saveMx(); renderMatrix(); refreshAvailability();
  };
  ['#e-avoid', '#e-needsol'].forEach(s => $(s).onchange = refreshAvailability);
  $$('.mode').forEach(b => b.onclick = () => setMode(b.dataset.mode));
  $('#cart-go').onclick = () => setMode('cart');
  $('#exp-exam').onclick = () => { setMode('cart'); $('#pop-export').hidden = true; };
  $('#cart-clear').onclick = () => { S.cart.clear(); saveCart(); renderGrid(); };
  $('#gen-btn').onclick = () => generate();
  renderMatrix();
}

/* ================= thanh công cụ ================= */
function setupToolbar() {
  const pops = [['#btn-filter', '#pop-filter'], ['#btn-export', '#pop-export']];
  pops.forEach(([b, p]) => $(b).onclick = e => {
    e.stopPropagation();
    const open = $(p).hidden;
    pops.forEach(([, q]) => $(q).hidden = true);
    $(p).hidden = !open; $(b).setAttribute('aria-expanded', open);
  });
  document.addEventListener('click', e => { if (!e.target.closest('.dd')) pops.forEach(([, q]) => $(q).hidden = true); });
  $('#f-sort').innerHTML = '<option value="tree">Sắp xếp: theo mục lục</option><option value="new">Sắp xếp: mới nhập</option><option value="least_used">Sắp xếp: ít dùng nhất</option>';
  $('#f-sort').value = S.sort;
  $('#f-sort').onchange = e => { S.sort = e.target.value; store('kd_sort', S.sort); loadList(); };
  $('#f-noans').onchange = e => { S.noans = e.target.checked; filtersChanged(); };
  $('#f-avoid').onchange = e => { S.avoid = e.target.checked; filtersChanged(); };
  $('#f-clear').onclick = () => { S.levels.clear(); S.types.clear(); S.noans = S.avoid = false; $('#f-noans').checked = $('#f-avoid').checked = false; filtersChanged(); };
  $('#sel-page').onclick = () => {
    const all = S.items.every(q => S.cart.has(q.id));
    S.items.forEach(q => all ? S.cart.delete(q.id) : S.cart.add(q.id)); saveCart(); renderGrid();
  };
  $$('.viewsw button').forEach(b => b.onclick = () => { S.view = b.dataset.v; store('kd_view', S.view); renderGrid(); });
  $('#pg-prev').onclick = () => gotoPage(S.page - 1);
  $('#pg-next').onclick = () => gotoPage(S.page + 1);
  let t;
  $('#f-text').oninput = e => { clearTimeout(t); t = setTimeout(() => { S.text = e.target.value.trim(); S.page = 1; refresh(); }, 300); };
  $$('[data-exp]').forEach(b => b.onclick = async () => {
    if (!S.cart.size) return toast('Chưa chọn câu nào — bấm “THÊM” trên các câu cần xuất');
    try { await download('/api/export', {ids: [...S.cart], solution: b.dataset.exp === '1'}, 'cau_hoi.docx'); toast('Đã xuất file Word'); }
    catch (e) { toast(e.message); }
  });
}
function setupSettings() {
  $('#btn-settings').onclick = async () => {
    $('#s-center').value = (await api('/api/settings')).center || '';
    const i = await api('/api/info');
    $('#s-info').innerHTML = `Kho đang lưu tại:<br><b>${esc(i.data_dir)}</b><br>${i.questions.toLocaleString('vi-VN')} câu hỏi · ${i.size_mb} MB`;
    $('#s-opendir').hidden = !DESK();
    $('#settings-dlg').showModal();
  };
  $('#s-backup').onclick = e => { e.preventDefault(); download('/api/backup', null, 'SaoLuu_KhoDeToan.db').then(r => r && !DESK() && toast('Đã tải bản sao lưu')).catch(err => toast(err.message)); };
  $('#s-codes').onclick = e => { e.preventDefault(); download('/api/folders/codes', null, 'Ma_chuyen_de.txt').catch(err => toast(err.message)); };
  $('#s-opendir').onclick = async e => { e.preventDefault(); window.pywebview.api.open_path(await window.pywebview.api.data_dir()); };
  $$('a[href="/mau-nhap-cau-hoi.docx"]').forEach(a => a.onclick = e => { e.preventDefault(); e.stopPropagation(); download('/mau-nhap-cau-hoi.docx', null, 'Mau_nhap_cau_hoi.docx').catch(err => toast(err.message)); });
  $('#s-save').onclick = async () => { await post('/api/settings', {center: $('#s-center').value}, 'PUT'); toast('Đã lưu cài đặt'); };
}

function setupTheme() {
  const dark = () => { const t = document.documentElement.dataset.theme; return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; };
  $('#btn-theme').onclick = () => { const t = dark() ? 'light' : 'dark'; document.documentElement.dataset.theme = t; store('kd_theme', t); };
}
/* ================= khởi động ================= */
(async function init() {
  setupTheme();
  setupToolbar(); renderFilterPop(); setupImport(); setupSettings(); setupDetail(); setupTreeUI();
  if (!S.sel.kind) S.sel = {type: 'all', kind: S.kind};
  await loadTrees();
  setupExam();
  refresh(); updateCart(); showView();
})();
