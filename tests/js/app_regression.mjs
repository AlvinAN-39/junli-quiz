/**
 * tests/js/app_regression.mjs — app/app.js 的用户可见行为回归（Node 沙箱）
 * =====================================================================
 * 与 app_contract.mjs 的分工：
 *   app_contract.mjs  → 数据契约 / 纯函数 / 启动吸收题库
 *   本文件            → **跨模块状态流转**：练习会话、错题重做、导入导出、
 *                       考试计分与进度、答题卡分页、顶栏与列表刷新
 *
 * 为什么必须有这一层：这些问题全部发生在「多个模块协作」处，
 * 既不属于数据形状，也不是单个纯函数能覆盖的，历史上因此漏检。
 * 做法与 app_contract.mjs 一致：node:vm + 最小 DOM 桩**真实执行** app/app.js，
 * 通过伪造的 document 事件监听器驱动真实点击 / 输入 / 按键，再读 window.__JLX__。
 *
 * 用法：node tests/js/app_regression.mjs
 * 输出：一行 JSON（{"checks":[{"name","ok","detail"}...]}），失败时 exit 1。
 */

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');

const appJs = fs.readFileSync(path.join(ROOT, 'app', 'app.js'), 'utf8');
const bank = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'questions.json'), 'utf8'));

const KEY_PROGRESS = 'jlx.progress.v1';
const KEY_SESSION = 'jlx.session.v1';
const KEY_SETTINGS = 'jlx.settings.v1';

const checks = [];
function check(name, ok, detail = '') {
  checks.push({ name, ok: !!ok, detail: String(detail) });
}

// ---------------------------------------------------------------------------
// 最小 DOM 桩（比 app_contract 多两件事：记录事件监听器、让 createElement 可点）
// ---------------------------------------------------------------------------
function makeEl(tag = 'div') {
  const el = {
    tagName: String(tag).toUpperCase(), children: [], childNodes: [], style: {}, dataset: {}, _on: {},
    classList: {
      _s: new Set(),
      add(...c) { c.forEach((x) => this._s.add(x)); },
      remove(...c) { c.forEach((x) => this._s.delete(x)); },
      toggle(c, f) { const on = f === undefined ? !this._s.has(c) : !!f; on ? this._s.add(c) : this._s.delete(c); return on; },
      contains(c) { return this._s.has(c); },
    },
    _text: '', _html: '',
    get textContent() { return this._text; },
    set textContent(v) { this._text = String(v); },
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); this.children.length = 0; },
    appendChild(c) { this.children.push(c); return c; },
    append(...c) { c.forEach((x) => this.children.push(x)); },
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    remove() {}, insertBefore(c) { this.children.unshift(c); return c; }, insertAdjacentHTML() {},
    setAttribute(k, v) { this['attr_' + k] = v; if (k === 'id') this.id = v; },
    getAttribute(k) { return this['attr_' + k] ?? null; },
    removeAttribute(k) { delete this['attr_' + k]; },
    hasAttribute(k) { return ('attr_' + k) in this; },
    addEventListener(t, f) { (this._on[t] = this._on[t] || []).push(f); },
    removeEventListener() {}, dispatchEvent() { return true; },
    focus() {}, blur() {}, click() {}, select() {}, scrollIntoView() {}, setSelectionRange() {},
    play() { return Promise.resolve(); }, pause() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    closest() { return null; }, contains() { return false; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 375, height: 667, bottom: 667, right: 375 }; },
    get firstChild() { return this.children[0] || null; },
    get lastChild() { return this.children[this.children.length - 1] || null; },
  };
  return el;
}

/** 每个用例一个全新沙箱（localStorage 可注入、可跨沙箱复用模拟「刷新」）。 */
async function build(store) {
  const byId = new Map();
  const elById = (id) => { if (!byId.has(id)) { const e = makeEl('div'); e.id = id; byId.set(id, e); } return byId.get(id); };
  const listeners = {};
  const doc = {
    readyState: 'complete',
    documentElement: Object.assign(makeEl('html'), { lang: '' }),
    head: makeEl('head'), body: makeEl('body'), title: '',
    createElement: (t) => makeEl(t), createElementNS: (_n, t) => makeEl(t),
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
    createDocumentFragment: () => makeEl('fragment'),
    getElementById: (id) => byId.get(id) || null,
    querySelector: (sel) => { const m = /^#([\w-]+)$/.exec(sel); return m ? elById(m[1]) : null; },
    querySelectorAll: () => [],
    addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
    removeEventListener() {}, dispatchEvent() { return true; },
  };
  const localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
    key: (i) => [...store.keys()][i] ?? null,
    get length() { return store.size; },
  };
  const sb = {
    console, setTimeout, clearTimeout, setInterval, clearInterval,
    document: doc, localStorage, sessionStorage: localStorage,
    location: { protocol: 'file:', href: 'file:///x/a.html', hash: '', search: '', reload() {} },
    navigator: {
      userAgent: 'node', language: 'zh-CN', languages: ['zh-CN'], onLine: true,
      clipboard: { writeText: async () => {} }, serviceWorker: undefined,
    },
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }),
    requestAnimationFrame: (cb) => setTimeout(() => cb(Date.now()), 0), cancelAnimationFrame: clearTimeout,
    alert() {}, confirm: () => true, prompt: () => null,
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
    Blob: class {}, FileReader: class { readAsText() {} },
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
    innerWidth: 390, innerHeight: 844, devicePixelRatio: 3, scrollTo() {},
    btoa: (s) => Buffer.from(s, 'binary').toString('base64'),
  };
  sb.window = sb; sb.globalThis = sb; sb.self = sb;
  sb.window.__QUESTION_BANK__ = bank;
  vm.runInContext(appJs, vm.createContext(sb), { filename: 'app.js' });
  await new Promise((r) => setTimeout(r, 20));   // 等 boot() 的题库 Promise 落地
  elById('modal-backdrop').hidden = true;        // index.html 里该节点带 hidden 属性
  return { sb, listeners, elById, store, J: sb.window.__JLX__ };
}

function fake(attrs) {
  const m = Object.assign({}, attrs);
  return {
    getAttribute: (k) => (k in m ? String(m[k]) : null), hasAttribute: (k) => k in m,
    parentNode: null, classList: { toggle() {} }, querySelector() { return null; }, value: m.value,
  };
}
const click = (h, act, a = {}) => {
  const el = fake(Object.assign({ 'data-act': act }, a));
  h.listeners['click'].forEach((f) => f({ target: el, preventDefault() {} }));
};
const nav = (h, route) => {
  const el = fake({ 'data-nav': route });
  h.listeners['click'].forEach((f) => f({ target: el, preventDefault() {} }));
};
const input = (h, act, a = {}) => {
  const el = fake(Object.assign({ 'data-act': act }, a));
  h.listeners['input'].forEach((f) => f({ target: el, preventDefault() {} }));
};
const key = (h, k) => {
  h.listeners['keydown'].forEach((f) => f({ key: k, target: null, ctrlKey: false, metaKey: false, altKey: false, preventDefault() {} }));
};
/** 点确认框里最后一个按钮（确定 / 交卷 / 离开 / 合并导入 …） */
const modalOk = (h) => {
  const foot = h.elById('modal-foot');
  const b = (foot.children || []).slice(-1)[0];
  const hs = b && b._on && b._on.click;
  if (!hs || !hs.length) return false;
  hs.forEach((f) => f({}));
  return true;
};
const modalOpen = (h) => h.elById('modal-backdrop').hidden === false;
const html = (h) => h.elById('view').innerHTML;
const qById = (h, id) => h.J.state.byId[id];

// ---------------------------------------------------------------------------
// R1–R2 判断题：只有 1/2 有效，3~9 不得提交
// ---------------------------------------------------------------------------
{
  const h = await build(new Map());
  const judge = bank.questions.find((q) => q.type === 'judge');
  click(h, 'q:practice', { 'data-id': judge.id });
  key(h, '3');
  check('R1 判断题按 3 不提交、不判错', !h.J.state.sess.res[judge.id],
    JSON.stringify(h.J.state.sess.res[judge.id] || null));

  const judgeTrue = bank.questions.find((q) => q.type === 'judge' && q.answer === true);
  const h2 = await build(new Map());
  click(h2, 'q:practice', { 'data-id': judgeTrue.id });
  key(h2, '1');
  const r = h2.J.state.sess.res[judgeTrue.id];
  check('R2 判断题按 1 正常判对', !!r && r.picked === true && r.ok === true, JSON.stringify(r || null));
}

// ---------------------------------------------------------------------------
// R3–R4 derive：seen=0 但已收藏 / 已标错的题必须计数
// ---------------------------------------------------------------------------
{
  const store = new Map();
  store.set(KEY_PROGRESS, JSON.stringify({
    'q-0001': { seen: 0, correct: 0, wrong: 0, lastTs: 0, box: 0, fav: true, wrongFlag: false },
  }));
  const h = await build(store);
  check('R3 未作答但已收藏计入 derive().fav', h.J.derive().fav === 1, 'fav=' + h.J.derive().fav);
}
{
  const store = new Map();
  store.set(KEY_PROGRESS, JSON.stringify({
    'q-0002': { seen: 0, correct: 0, wrong: 0, lastTs: 0, box: 0, fav: false, wrongFlag: true },
  }));
  const h = await build(store);
  check('R4 未作答但标错计入 derive().wrong', h.J.derive().wrong === 1, 'wrong=' + h.J.derive().wrong);
}

// ---------------------------------------------------------------------------
// R5–R6 合并导入：保住本机按日记录；统计缓存必须失效
// ---------------------------------------------------------------------------
{
  const store = new Map();
  store.set(KEY_PROGRESS, JSON.stringify({
    __daily: { '2026-10-01': { n: 5, ok: 4 } },
    'q-0001': { seen: 1, correct: 1, wrong: 0, lastTs: 1, box: 1, fav: false, wrongFlag: false },
    'q-0002': { seen: 1, correct: 0, wrong: 1, lastTs: 1, box: 1, fav: false, wrongFlag: true },
  }));
  const h = await build(store);
  nav(h, 'sync');                                   // 该页 render 时会填充统计缓存
  check('R5a 导入前 derive().done = 2', h.J.derive().done === 2, 'done=' + h.J.derive().done);
  h.elById('import-area').value = JSON.stringify({
    progress: { 'q-0003': { seen: 1, correct: 1, wrong: 0, lastTs: 2, box: 1, fav: false, wrongFlag: false } },
    daily: { '2026-10-02': { n: 3, ok: 3 } },
  });
  click(h, 'sync:merge');
  check('R5b 合并导入确认框可触发', modalOk(h));
  const daily = h.J.state.progress.__daily;
  check('R5c 合并导入保留本机按日记录', !!daily['2026-10-01'] && !!daily['2026-10-02'], JSON.stringify(daily));
  check('R6 合并导入后统计缓存失效并重算', h.J.derive().done === 3, 'done=' + h.J.derive().done);
}

// ---------------------------------------------------------------------------
// R7 清空本机数据：练习会话必须一起作废
// ---------------------------------------------------------------------------
{
  const store = new Map();
  store.set(KEY_PROGRESS, JSON.stringify({
    'q-0001': { seen: 1, correct: 1, wrong: 0, lastTs: 1, box: 1, fav: false, wrongFlag: false },
  }));
  const h = await build(store);
  click(h, 'q:practice', { 'data-id': 'q-0001' });
  check('R7a 练习会话已落盘', !!store.get(KEY_SESSION));
  nav(h, 'sync');
  click(h, 'sync:reset');
  check('R7b 清空确认框可触发', modalOk(h));
  check('R7c 清空后磁盘会话被删除', !store.get(KEY_SESSION));
  check('R7d 清空后不再可恢复', h.J.sessionProbe().hasResumable === false, JSON.stringify(h.J.sessionProbe()));
}

// ---------------------------------------------------------------------------
// R8 错题重做：退出/刷新后继续，答对仍要移出错题本
// ---------------------------------------------------------------------------
{
  const store = new Map();
  const prog = {};
  for (let i = 1; i <= 5; i++) prog['q-000' + i] = { seen: 1, correct: 0, wrong: 1, lastTs: 1, box: 1, fav: false, wrongFlag: true };
  store.set(KEY_PROGRESS, JSON.stringify(prog));
  const h = await build(store);
  click(h, 'wrong:redo');
  check('R8a 错题重做进入 wrongMode', h.J.state.sess && h.J.state.sess.wrongMode === true, '');
  const saved = JSON.parse(store.get(KEY_SESSION) || 'null');
  check('R8b 落盘的会话带上 wrongMode', !!(saved && saved.wrongMode === true), 'keys=' + (saved ? Object.keys(saved).join(',') : 'null'));

  const h2 = await build(store);                    // 模拟刷新
  click(h2, 'prac:continue');
  const s2 = h2.J.state.sess;
  check('R8c 刷新续练仍是错题重做模式', !!(s2 && s2.wrongMode === true), 'wrongMode=' + (s2 && s2.wrongMode));
  const first = s2.ids[0];
  const q = qById(h2, first);
  if (q && q.type === 'single') {
    click(h2, 'ans:pick', { 'data-k': q.qa });
    check('R8d 续练中答对自动移出错题本', h2.J.state.progress[first].wrongFlag === false,
      'wrongFlag=' + h2.J.state.progress[first].wrongFlag);
  } else {
    check('R8d 续练中答对自动移出错题本', false, 'first=' + first + ' type=' + (q && q.type));
  }
}

// ---------------------------------------------------------------------------
// R9 会话恢复：选项乱序排列与未提交草稿
// ---------------------------------------------------------------------------
{
  const store = new Map();
  store.set(KEY_SETTINGS, JSON.stringify({ shuffleOptions: true }));
  const multi = bank.questions.find((q) => q.type === 'multi');
  const h = await build(store);
  click(h, 'q:practice', { 'data-id': multi.id });
  click(h, 'ans:pick', { 'data-k': 'A' });
  await new Promise((r) => setTimeout(r, 150));     // 等 saveSessionSoon 落盘
  const saved = JSON.parse(store.get(KEY_SESSION) || 'null');
  check('R9a 会话落盘带 draft', !!(saved && saved.draft && saved.draft[multi.id]), 'keys=' + (saved ? Object.keys(saved).join(',') : 'null'));
  const savedPerm = saved && saved.perm ? saved.perm[multi.id] : null;
  check('R9b 会话落盘带 perm（选项乱序排列）', Array.isArray(savedPerm) && savedPerm.length === multi.options.length,
    JSON.stringify(savedPerm || null));

  const h2 = await build(store);
  click(h2, 'prac:continue');
  const s2 = h2.J.state.sess;
  check('R9c 续练恢复未提交勾选', Array.isArray(s2.draft[multi.id]) && s2.draft[multi.id].indexOf('A') >= 0,
    JSON.stringify(s2.draft[multi.id] || null));
  check('R9d 续练恢复的选项排列与退出前一致',
    Array.isArray(s2.perm[multi.id]) && JSON.stringify(s2.perm[multi.id]) === JSON.stringify(savedPerm),
    'before=' + JSON.stringify(savedPerm) + ' after=' + JSON.stringify(s2.perm[multi.id] || null));
}

// ---------------------------------------------------------------------------
// R10 答题卡分页标题区间
// ---------------------------------------------------------------------------
{
  const h = await build(new Map());
  click(h, 'prac:start');
  click(h, 'grid:toggle');
  const m1 = /答题卡<span class="card-sub">([^<]*)/.exec(html(h));
  check('R10a 答题卡第 1 页区间为 1-100', !!m1 && m1[1].trim().startsWith('1-100'), 'sub=' + (m1 && m1[1]));
  click(h, 'grid:page', { 'data-v': '2' });
  const m2 = /答题卡<span class="card-sub">([^<]*)/.exec(html(h));
  check('R10b 答题卡第 2 页区间为 101-200', !!m2 && m2[1].trim().startsWith('101-200'), 'sub=' + (m2 && m2[1]));
}

// ---------------------------------------------------------------------------
// R11–R13 考试：提示文案、无死按钮、未作答题不计进度
// ---------------------------------------------------------------------------
{
  const h = await build(new Map());
  click(h, 'exam:new');
  click(h, 'exam:count', { 'data-v': '5' });
  click(h, 'exam:start');
  const st = h.J.state;
  check('R11a 考试进入 run', !!st.exam && st.exam.phase === 'run', 'phase=' + (st.exam && st.exam.phase));

  const singleIdx = st.exam.ids.findIndex((id) => qById(h, id).type === 'single');
  click(h, 'nav:jump', { 'data-i': singleIdx });
  check('R11b 考试中单选题不显示「点选即判分」', html(h).indexOf('点选即判分') < 0, '');
  check('R11c 考试中显示中性提示', html(h).indexOf('考试中不判定对错') >= 0, '');

  const multiIdx = st.exam.ids.findIndex((id) => qById(h, id).type === 'multi');
  if (multiIdx >= 0) {
    click(h, 'nav:jump', { 'data-i': multiIdx });
    check('R12a 考试中多选题不显示「提交答案」按钮', html(h).indexOf('提交答案') < 0, '');
    check('R12b 考试中多选题不显示「选好后点」提示', html(h).indexOf('选好后点') < 0, '');
  } else {
    check('R12a 考试中多选题不显示「提交答案」按钮', true, '本次未抽到多选题，跳过');
    check('R12b 考试中多选题不显示「选好后点」提示', true, '本次未抽到多选题，跳过');
  }

  // 只答第一题，其余留空 → 交卷
  const firstId = st.exam.ids[0];
  const fq = qById(h, firstId);
  click(h, 'nav:jump', { 'data-i': 0 });
  if (fq.type === 'single') click(h, 'ans:pick', { 'data-k': fq.qa });
  else if (fq.type === 'judge') click(h, 'ans:pick', { 'data-k': fq.qa ? 'true' : 'false' });
  else if (fq.type === 'multi') click(h, 'ans:pick', { 'data-k': fq.qa[0] });
  else if (fq.type === 'fill') input(h, 'ans:fill', { 'data-i': '0', value: 'x' });
  else input(h, 'ans:short', { value: 'x' });
  click(h, 'exam:submit');
  check('R13a 交卷确认框可触发', modalOk(h));
  check('R13b 未作答的题不写入学习进度', h.J.derive().done === 1, 'done=' + h.J.derive().done + ' (应为 1)');
  const untouched = st.exam.ids.filter((id) => !h.J.state.progress[id]);
  check('R13c 未作答题没有 progress 条目', untouched.length === st.exam.ids.length - 1,
    'untouched=' + untouched.length + '/' + (st.exam.ids.length - 1));
  const day = h.J.derive().days[h.J.derive().days.length - 1];
  check('R13d 每日做题量只记实际作答', day.n === 1, 'today.n=' + day.n);
}

// ---------------------------------------------------------------------------
// R14 收藏夹列表里取消收藏
// ---------------------------------------------------------------------------
{
  const store = new Map();
  store.set(KEY_PROGRESS, JSON.stringify({
    'q-0001': { seen: 1, correct: 1, wrong: 0, lastTs: 1, box: 1, fav: true, wrongFlag: false },
  }));
  const h = await build(store);
  nav(h, 'fav');
  check('R14a 收藏夹列出 1 题', html(h).indexOf('1 题') >= 0, '');
  click(h, 'fav', { 'data-id': 'q-0001' });
  check('R14b 取消后列表即时移除该题', html(h).indexOf('收藏夹') < 0 || html(h).indexOf('还没有收藏题目') >= 0, html(h).slice(0, 80));
}

// ---------------------------------------------------------------------------
// R15 顶栏不再串用另一种模式的会话
// ---------------------------------------------------------------------------
{
  const h = await build(new Map());
  click(h, 'recite:start');
  nav(h, 'practice');
  const title = h.elById('page-title').textContent;
  check('R15a 练习设置页顶栏不再显示背题标题', title.indexOf('背题') < 0, 'title=' + title);
  check('R15b 练习设置页确实渲染了设置内容', html(h).indexOf('练习设置') >= 0, '');
}

// ---------------------------------------------------------------------------
// R16 考试进行中离开要先确认
// ---------------------------------------------------------------------------
{
  const h = await build(new Map());
  click(h, 'exam:new');
  click(h, 'exam:start');
  nav(h, 'home');
  check('R16a 点首页被确认框拦住（未直接离开）', h.J.state.route === 'exam' && modalOpen(h),
    'route=' + h.J.state.route + ' modal=' + modalOpen(h));
  modalOk(h);
  check('R16b 确认后才真正离开', h.J.state.route === 'home', 'route=' + h.J.state.route);
}

// ---------------------------------------------------------------------------
// R17 设置页主题三态可选
// ---------------------------------------------------------------------------
{
  const h = await build(new Map());
  nav(h, 'settings');
  check('R17a 设置页不因 serviceWorker 取用而渲染出错', html(h).indexOf('页面渲染出错') < 0, html(h).slice(0, 120));
  const hasThree = ['跟随系统', '浅色', '深色'].every((n) => html(h).indexOf('>' + n + '<') >= 0);
  check('R17b 设置页主题为三态按钮', hasThree, '');
  click(h, 'set:theme', { 'data-v': 'dark' });
  check('R17c 可直接选深色', h.J.state.settings.theme === 'dark', 'theme=' + h.J.state.settings.theme);
}

// ---------------------------------------------------------------------------
// 汇总
// ---------------------------------------------------------------------------
const failed = checks.filter((c) => !c.ok);
console.log(JSON.stringify({ suite: 'app_regression', pass: checks.length - failed.length, fail: failed.length, checks }, null, 1));
process.exit(failed.length ? 1 : 0);
