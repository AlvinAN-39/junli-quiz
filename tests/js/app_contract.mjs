/**
 * tests/js/app_contract.mjs — 在 Node 里跑 app/app.js 的核心逻辑契约测试
 * =====================================================================
 *
 * 为什么不用真浏览器：项目要求「零第三方依赖」，Playwright/Puppeteer 不在依赖里。
 * 这里用**最小 DOM 桩** + node:vm 执行真实的 app.js，只验证与数据契约有关、
 * 不需要布局与事件的部分：
 *   · normalizeAnswer 必须严格实现 docs/02-data-contract.md 第 2 节；
 *   · 全量 1531 题都能被 hydrate/buildBank 吸收，且题型与答案形态正确；
 *   · 断网兜底的 MOCK_BANK 自身也必须符合契约（它是 file:// 下唯一的题库）；
 *   · 导出的调试接口（__JLX__）键名稳定。
 *
 * 用法：node tests/js/app_contract.mjs
 * 输出：一行 JSON（{"checks":[{"name","ok","detail"}...]}），失败时 exit 1。
 */

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');

const checks = [];
function check(name, ok, detail = '') {
  checks.push({ name, ok: !!ok, detail: String(detail) });
}

// ---------------------------------------------------------------------------
// 最小 DOM 桩
// ---------------------------------------------------------------------------
function makeEl(tag = 'div') {
  const el = {
    tagName: String(tag).toUpperCase(),
    children: [], childNodes: [], style: {}, dataset: {},
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
    get innerText() { return this._text; },
    set innerText(v) { this._text = String(v); },
    appendChild(c) { this.children.push(c); return c; },
    append(...c) { c.forEach((x) => this.children.push(x)); },
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    remove() {}, insertBefore(c) { this.children.unshift(c); return c; },
    insertAdjacentHTML() {},
    setAttribute(k, v) { this['attr_' + k] = v; if (k === 'id') this.id = v; },
    getAttribute(k) { return this['attr_' + k] ?? null; },
    removeAttribute(k) { delete this['attr_' + k]; },
    hasAttribute(k) { return k in this; },
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
    focus() {}, blur() {}, click() {}, select() {}, scrollIntoView() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    closest() { return null; }, contains() { return false; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 375, height: 667, bottom: 667, right: 375 }; },
    get firstChild() { return this.children[0] || null; },
    get lastChild() { return this.children[this.children.length - 1] || null; },
  };
  return el;
}

const byId = new Map();
function elById(id) {
  if (!byId.has(id)) { const e = makeEl('div'); e.id = id; byId.set(id, e); }
  return byId.get(id);
}

const doc = {
  readyState: 'complete',
  documentElement: Object.assign(makeEl('html'), { lang: '' }),
  head: makeEl('head'),
  body: makeEl('body'),
  title: '',
  createElement: (t) => makeEl(t),
  createElementNS: (_ns, t) => makeEl(t),
  createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
  createDocumentFragment: () => makeEl('fragment'),
  getElementById: (id) => byId.get(id) || null,
  querySelector: (sel) => {
    const m = /^#([\w-]+)$/.exec(sel);
    if (m) return elById(m[1]);
    return null;
  },
  querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
  dispatchEvent() { return true; },
};

const store = new Map();
const localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
  key: (i) => [...store.keys()][i] ?? null,
  get length() { return store.size; },
};

const sandbox = {
  console, setTimeout, clearTimeout, setInterval, clearInterval,
  document: doc, localStorage, sessionStorage: localStorage,
  location: { protocol: 'file:', href: 'file:///x/军理刷题.html', hash: '', search: '', reload() {} },
  navigator: {
    userAgent: 'node', language: 'zh-CN', languages: ['zh-CN'], onLine: true,
    clipboard: { writeText: async () => {} }, serviceWorker: undefined,
  },
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }),
  requestAnimationFrame: (cb) => setTimeout(() => cb(Date.now()), 0),
  cancelAnimationFrame: clearTimeout,
  alert() {}, confirm: () => true, prompt: () => null,
  URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
  Blob: class { constructor() {} }, FileReader: class { readAsText() {} },
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
  addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
  innerWidth: 390, innerHeight: 844, devicePixelRatio: 3, scrollTo() {},
  window: null,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.self = sandbox;

const bank = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'questions.json'), 'utf8'));
sandbox.window.__QUESTION_BANK__ = bank;

const appJs = fs.readFileSync(path.join(ROOT, 'app', 'app.js'), 'utf8');
const ctx = vm.createContext(sandbox);
let loadError = '';
try {
  vm.runInContext(appJs, ctx, { filename: 'app.js' });
} catch (e) {
  loadError = String((e && e.stack) || e);
}
check('app.js 可执行（无异常）', !loadError, loadError.split('\n').slice(0, 3).join(' | '));

const J = sandbox.window.__JLX__;
check('window.__JLX__ 已暴露', !!J);

const EXPECTED_KEYS = ['version', 'state', 'derive', 'deriveUncached', 'outline',
  'outlineMarkdown', 'exportText', 'normalizeAnswer', 'sessionProbe', 'feedback', 'MOCK_BANK'];
if (J) {
  const missing = EXPECTED_KEYS.filter((k) => !(k in J));
  check('__JLX__ 键名稳定（T5/T6 依赖）', missing.length === 0, 'missing=' + missing.join(','));
}

// ---------------------------------------------------------------------------
// normalizeAnswer：严格按 docs/02-data-contract.md 第 2 节
// ---------------------------------------------------------------------------
if (J && typeof J.normalizeAnswer === 'function') {
  const n = J.normalizeAnswer;
  const cases = [
    ['single 大写字母', { type: 'single', answer: 'A' }, (v) => v === 'A'],
    ['single 小写/带空格归一化', { type: 'single', answer: ' b ' }, (v) => v === 'B'],
    ['multi 数组去重排序', { type: 'multi', answer: ['C', 'A'] }, (v) => Array.isArray(v) && v.join(',') === 'A,C'],
    ['multi 字符串按字符切分', { type: 'multi', answer: 'AB' }, (v) => Array.isArray(v) && v.join(',') === 'A,B'],
    ['judge true', { type: 'judge', answer: true }, (v) => v === true],
    ['judge 字符串 true', { type: 'judge', answer: 'true' }, (v) => v === true],
    ['judge 对', { type: 'judge', answer: '对' }, (v) => v === true],
    ['judge 正确', { type: 'judge', answer: '正确' }, (v) => v === true],
    ['judge false', { type: 'judge', answer: false }, (v) => v === false],
    ['fill 数组', { type: 'fill', answer: ['x'] }, (v) => Array.isArray(v) && v.join(',') === 'x'],
    ['fill 标量', { type: 'fill', answer: 'y' }, (v) => Array.isArray(v) && v.join(',') === 'y'],
    ['short 原样字符串', { type: 'short', answer: 'z' }, (v) => v === 'z'],
    ['未知题型按字符串处理', { type: 'weird', answer: 'q' }, (v) => v === 'q'],
    ['answer 为 undefined 不抛错', { type: 'short' }, (v) => v === ''],
  ];
  const failed = [];
  for (const [name, input, ok] of cases) {
    try {
      const got = n(input);
      if (!ok(got)) failed.push(name + ' -> ' + JSON.stringify(got));
    } catch (e) { failed.push(name + ' 抛错 ' + e.message); }
  }
  check('normalizeAnswer 契约用例', failed.length === 0, failed.join('; '));

  // 全量题库
  const LETTERS = 'ABCDEFGH';
  const shapeBad = [];
  let ok = 0;
  for (const q of bank.questions) {
    try {
      const v = n(q);
      let good = false;
      if (q.type === 'single') good = typeof v === 'string' && LETTERS.includes(v) && LETTERS.indexOf(v) < q.options.length;
      else if (q.type === 'multi') good = Array.isArray(v) && v.length >= 2
        && v.every((x) => LETTERS.includes(x)) && v.join(',') === [...new Set(v)].sort().join(',')
        && LETTERS.indexOf(v[v.length - 1]) < q.options.length;
      else if (q.type === 'judge') good = typeof v === 'boolean';
      else if (q.type === 'fill') good = Array.isArray(v) && v.length >= 1 && v.every((x) => typeof x === 'string' && x.length > 0);
      else if (q.type === 'short') good = typeof v === 'string' && v.length > 0;
      if (good) ok++; else shapeBad.push(q.id + ':' + q.type + ' -> ' + JSON.stringify(v).slice(0, 40));
    } catch (e) { shapeBad.push(q.id + ' 抛错 ' + e.message); }
  }
  check('全量题库 normalizeAnswer 形态正确', shapeBad.length === 0,
    ok + '/' + bank.questions.length + (shapeBad.length ? ' bad=' + shapeBad.slice(0, 5).join(' ') : ''));
}

// ---------------------------------------------------------------------------
// 启动后 State 必须吸收全部题目（buildBank/hydrate 不得丢题）
// ---------------------------------------------------------------------------
await new Promise((r) => setTimeout(r, 100));
if (J && J.state) {
  const qs = J.state.questions || [];
  check('State.questions 吸收全量题目', qs.length === bank.questions.length,
    qs.length + ' / ' + bank.questions.length + ' from=' + J.state.from);
  const byIdCount = Object.keys(J.state.byId || {}).length;
  check('State.byId 索引与题量一致', byIdCount === qs.length, byIdCount + ' vs ' + qs.length);
  const badType = qs.filter((q) => !['single', 'multi', 'judge', 'fill', 'short'].includes(q.type));
  check('hydrate 后题型合法', badType.length === 0, badType.slice(0, 3).map((q) => q.id).join(','));
  const noQa = qs.filter((q) => q.qa === undefined || q.qa === null);
  check('hydrate 后 qa 已归一化', noQa.length === 0, noQa.slice(0, 3).map((q) => q.id).join(','));
}

// ---------------------------------------------------------------------------
// MOCK_BANK：断网兜底题库自身必须符合契约
// ---------------------------------------------------------------------------
if (J && J.MOCK_BANK) {
  const m = J.MOCK_BANK.questions || [];
  check('MOCK_BANK 至少 12 题', m.length >= 12, 'n=' + m.length);
  const types = new Set(m.map((q) => q.type));
  check('MOCK_BANK 覆盖 5 种题型', ['single', 'multi', 'judge', 'fill', 'short'].every((t) => types.has(t)),
    [...types].join(','));
  const ids = new Set(m.map((q) => q.id));
  check('MOCK_BANK id 唯一', ids.size === m.length, ids.size + '/' + m.length);
  const bad = [];
  for (const q of m) {
    if (!q.stem || !String(q.stem).trim()) bad.push(q.id + ':stem');
    if (!q.explanation || !String(q.explanation).trim()) bad.push(q.id + ':explanation');
    if ((q.type === 'single' || q.type === 'multi') && (!Array.isArray(q.options) || q.options.length < 2)) bad.push(q.id + ':options');
    if (!['single', 'multi', 'judge', 'fill', 'short'].includes(q.type)) bad.push(q.id + ':type');
  }
  check('MOCK_BANK 字段齐全', bad.length === 0, bad.slice(0, 5).join(','));
}

// ---------------------------------------------------------------------------
// 只读探针接口
// ---------------------------------------------------------------------------
if (J) {
  try {
    const probe = J.sessionProbe();
    check('sessionProbe 返回稳定结构',
      probe && typeof probe === 'object' && 'hasResumable' in probe && 'stored' in probe,
      JSON.stringify(probe).slice(0, 120));
  } catch (e) { check('sessionProbe 可调用', false, e.message); }

  try {
    const t = J.exportText();
    check('exportText 返回字符串', typeof t === 'string' && t.length > 0, typeof t + ' len=' + String(t).length);
  } catch (e) { check('exportText 可调用', false, e.message); }
}

// app.js 必须是普通脚本（bundle.py 靠字符串内联）
check('app.js 不含 ESM 语法', !/^\s*(import|export)\s/m.test(appJs));

const failed = checks.filter((c) => !c.ok);
console.log(JSON.stringify({ checks, failed: failed.length }, null, 1));
process.exit(failed.length ? 1 : 0);
