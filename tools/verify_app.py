#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_app.py — 无依赖静态体检：单文件产物 + PWA 产物 + JS 语法
================================================================

不依赖浏览器：用 Node 的 `--check` 做语法校验，并做一系列结构性断言
（题库是否内联、是否有外部请求、manifest 是否合法、SW 是否注册、契约键名是否一致）。
若环境里存在 Playwright/Puppeteer 则额外跑一次真实渲染，否则跳过并明确说明。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = ROOT / "app"
NODE = Path(os.environ.get("NODE_BIN", "").strip() or shutil.which("node") or "node")

PASS, FAIL, WARN = "[PASS]", "[FAIL]", "[WARN]"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "", warn_only: bool = False) -> None:
    tag = PASS if ok else (WARN if warn_only else FAIL)
    results.append((tag, name, detail))
    print(f"{tag} {name}" + (f" — {detail}" if detail else ""))


def node_check(path: Path) -> tuple[bool, str]:
    if not NODE.exists():
        return False, f"node 不存在: {NODE}"
    r = subprocess.run([str(NODE), "--check", str(path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode == 0, out.strip()[:400]


def main() -> int:
    single = DIST / "军理刷题.html"
    web = DIST / "web"

    print("=" * 78)
    print("军理刷题 — 产物静态体检")
    print("=" * 78)

    # ---------- 1. 源文件 JS 语法 ----------
    for js in (APP / "app.js", APP / "sw.js"):
        if js.exists():
            ok, msg = node_check(js)
            check(f"node --check {js.parent.name}/{js.name}", ok, msg)

    # ---------- 2. manifest 合法 JSON ----------
    mf = APP / "manifest.webmanifest"
    if mf.exists():
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            check("manifest.webmanifest 是合法 JSON",
                  bool(data.get("name")), f"name={data.get('name')!r} start_url={data.get('start_url')!r}")
        except Exception as e:
            check("manifest.webmanifest 是合法 JSON", False, str(e))

    # ---------- 3. 单文件版 ----------
    check("dist/军理刷题.html 存在", single.exists(),
          f"{single.stat().st_size / 1024:.0f} KB" if single.exists() else "")
    if single.exists():
        html = single.read_text(encoding="utf-8")
        check("题库已内联 (window.__QUESTION_BANK__)",
              "window.__QUESTION_BANK__" in html)
        check("无外部 http(s) 资源引用",
              not re.search(r'(?:src|href)\s*=\s*["\'](?:https?:)?//', html))
        check("无残留外部 <script src>",
              not re.search(r'<script[^>]+src=', html))
        check("无残留外部 <link rel=stylesheet>",
              not re.search(r'<link[^>]+stylesheet', html))
        check("样式已内联", "<style" in html)
        m = re.search(r"window\.__QUESTION_BANK__\s*=\s*(\{.*?\});\s*\n</script>",
                      html, re.S)
        if m:
            try:
                bank = json.loads(m.group(1))
                n = len(bank.get("questions", []))
                check("内联题库可 JSON 解析且题数 > 0", n > 0,
                      f"{n} 题 counts={bank.get('counts')}")
                # 契约字段抽样
                q = bank["questions"][0]
                need = {"id", "type", "stem", "options", "answer",
                        "explanation", "source", "chapter", "section"}
                check("契约字段齐全", need.issubset(q.keys()),
                      f"缺 {sorted(need - set(q.keys()))}" if not need.issubset(q.keys()) else "")

                # ---- 界面答案一致性（本轮新增）----------------------------------
                # 界面上有两处答案：判分/「参考答案」走 q.answer，
                # 解析块「正确答案」行走 explanationParts.answer。
                # 两者不一致时，同一屏会显示两套答案（本轮实测缺陷：q-0539）。
                bad = []
                for x in bank["questions"]:
                    if x.get("type") not in ("single", "multi"):
                        continue
                    pa = (x.get("explanationParts") or {}).get("answer") or ""
                    # 多选解析的写法有三种实测形态：
                    #   ①「A、B、C、D（捍卫国家主权；…）」  ②「A、私有制；C、阶级」  ③「A、选项文字」
                    # 任何一种「截取连续字母」的做法都会漏（2026-10-08 扩容时实测 77+306 处误报）。
                    # 改为最直接的口径：**对本题每个选项字母，逐个检查它是否以「字母+分隔符」出现在解析里**。
                    got = []
                    for i in range(len(x.get("options") or [])):
                        c = chr(65 + i)
                        if re.search(re.escape(c) + r"\s*[、,，/；;（(]", pa) or pa.rstrip().endswith(c):
                            got.append(c)
                    a = x.get("answer")
                    want = sorted(a if isinstance(a, list) else [str(a).strip().upper()])
                    if got and got != want:
                        bad.append(x["id"])
                check("解析块「正确答案」与答案字段一致", not bad,
                      f"不一致 {len(bad)} 题：{bad[:5]}" if bad else f"抽查 {n} 题全一致")
            except Exception as e:
                check("内联题库可 JSON 解析", False, str(e))
        else:
            check("能从 HTML 中提取内联题库", False, "未匹配到注入语句")

    # ---------- 4. PWA 版 ----------
    if web.exists():
        idx = web / "index.html"
        check("dist/web/index.html 存在", idx.exists())
        if idx.exists():
            h = idx.read_text(encoding="utf-8")
            check("PWA 版带静态 manifest",
                  "manifest.webmanifest" in h)
            check("PWA 版注册 Service Worker",
                  "serviceWorker" in h)
            # 部署目录不再夹带 data/：题库与提纲都已内联，这两个文件在正常产物里
            # 永远不会被请求，实测白占部署包约 45% 体积。
            check("PWA 版不夹带未被读取的 data/ 文件",
                  not (web / "data").exists(),
                  "data/ 仍在（题库/提纲已内联，属冗余）" if (web / "data").exists() else "")
            sw = web / "sw.js"
            if sw.exists():
                ok, msg = node_check(sw)
                check("dist/web/sw.js 语法", ok, msg)
            for f in ("app.css", "app.js", "manifest.webmanifest",
                      "icons/icon.svg"):
                check(f"dist/web/{f} 存在", (web / f).exists())

    # ---------- 5. 契约键名 ----------
    js = (APP / "app.js").read_text(encoding="utf-8") if (APP / "app.js").exists() else ""
    for key in ("jlx.progress.v1", "jlx.settings.v1", "jlx.exams.v1", "jlx.meta.v1"):
        check(f"localStorage 契约键名 {key}", key in js)
    check("app.js 无 ESM (import/export)",
          not re.search(r"^\s*(import|export)\s", js, re.M))

    # ---------- 6. 无头浏览器（可选） ----------
    print("-" * 78)
    pw_dir = Path(os.environ.get("QA_ENV", "").strip() or (ROOT.parent / "qa-env"))
    pw_cli = pw_dir / "node_modules" / "playwright" / "cli.js"
    has_pw = pw_cli.exists()
    check("Playwright 可用（真实渲染测试）", has_pw,
          f"已安装: {pw_cli.parent}" if has_pw
          else "未安装（见 README「验收」一节；Node 沙箱已覆盖核心逻辑）",
          warn_only=True)
    if has_pw and NODE.exists():
        for name in ("browser_test.mjs", "pwa_offline_test.mjs", "uncertainty_test.mjs"):
            src = ROOT / "qa" / name
            if not src.exists():
                continue
            dst = pw_dir / name
            shutil.copy2(src, dst)
            r = subprocess.run([str(NODE), str(dst)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", cwd=str(pw_dir))
            tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
            summary = next((l for l in reversed(tail) if "通过" in l or "合计" in l), "")
            check(f"浏览器测试 {name}", r.returncode == 0, summary.strip())
            if r.returncode != 0:
                for l in tail[-14:]:
                    print("      | " + l)

    # ---------- 7. Node 沙箱：直接跑 app.js 的核心逻辑 ----------
    harness = ROOT / "qa" / "headless_harness.mjs"
    harness.parent.mkdir(parents=True, exist_ok=True)
    harness.write_text(HARNESS_JS, encoding="utf-8")
    if NODE.exists():
        r = subprocess.run([str(NODE), str(harness)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=str(ROOT))
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        print("-" * 78)
        print("Node 沙箱运行结果：")
        print(out[:4000])
        check("Node 沙箱执行 app.js（无异常）", r.returncode == 0,
              f"exit={r.returncode}")

    print("=" * 78)
    n_fail = sum(1 for t, _, _ in results if t == FAIL)
    n_warn = sum(1 for t, _, _ in results if t == WARN)
    print(f"合计 {len(results)} 项：通过 {len(results) - n_fail - n_warn}，"
          f"失败 {n_fail}，警告 {n_warn}")
    return 1 if n_fail else 0


HARNESS_JS = r"""
// headless_harness.mjs — 在 Node 里用最小 DOM 桩执行 app.js，验证核心流程
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const ROOT = process.cwd();
const appJs = fs.readFileSync(path.join(ROOT, 'app', 'app.js'), 'utf8');
const bankPath = path.join(ROOT, 'data', 'questions.json');
const bank = JSON.parse(fs.readFileSync(bankPath, 'utf8'));

// ---- 最小 DOM 桩 ----
function makeEl(tag = 'div') {
  const el = {
    tagName: String(tag).toUpperCase(),
    children: [], childNodes: [], style: {}, dataset: {}, classList: {
      _s: new Set(),
      add(...c) { c.forEach(x => this._s.add(x)); },
      remove(...c) { c.forEach(x => this._s.delete(x)); },
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
    append(...c) { c.forEach(x => this.children.push(x)); },
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    remove() {},
    insertBefore(c) { this.children.unshift(c); return c; },
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
  navigator: { userAgent: 'node', language: 'zh-CN', languages: ['zh-CN'], onLine: true,
               clipboard: { writeText: async () => {} }, serviceWorker: undefined },
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {},
                       addListener() {}, removeListener() {} }),
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
sandbox.window.__QUESTION_BANK__ = bank;

const ctx = vm.createContext(sandbox);
let loaded = true, loadErr = '';
try {
  vm.runInContext(appJs, ctx, { filename: 'app.js' });
} catch (e) {
  loaded = false; loadErr = String(e && e.stack || e);
}

const out = [];
out.push('app.js 执行: ' + (loaded ? 'OK' : 'FAILED'));
if (!loaded) out.push(loadErr);

const J = sandbox.window.__JLX__;
out.push('window.__JLX__ 暴露: ' + (J ? 'YES' : 'NO'));
if (J) {
  out.push('暴露的键: ' + Object.keys(J).join(', '));
  const MOCK = J.MOCK_BANK;
  out.push('MOCK_BANK 题数: ' + (MOCK && MOCK.questions ? MOCK.questions.length : 'N/A'));
  // 归一化函数逐题型验证
  const cases = [
    { type: 'single', answer: 'A', want: 'A' },
    { type: 'multi', answer: ['C', 'A'], want: 'A,C' },
    { type: 'judge', answer: true, want: 'true' },
    { type: 'judge', answer: '对', want: 'true' },
    { type: 'fill', answer: ['x'], want: 'x' },
    { type: 'short', answer: 'y', want: 'y' },
  ];
  let ok = 0;
  for (const c of cases) {
    try {
      const got = J.normalizeAnswer(c);
      const g = Array.isArray(got) ? got.join(',') : String(got);
      if (g === c.want) ok++;
      else out.push('  normalizeAnswer 不符: ' + JSON.stringify(c) + ' -> ' + g);
    } catch (e) { out.push('  normalizeAnswer 抛错: ' + String(e)); }
  }
  out.push('normalizeAnswer 契约用例: ' + ok + '/' + cases.length);
  // 导出文本可生成
  try {
    const t = typeof J.exportText === 'function' ? J.exportText() : null;
    out.push('exportText 可调用: ' + (t ? ('YES (' + String(t).length + ' 字符)') : 'NO'));
  } catch (e) { out.push('exportText 抛错: ' + String(e)); }
}

// 关键：真实题库能被 normalize 处理而不抛错
let normalized = 0, bad = 0;
if (J && typeof J.normalizeAnswer === 'function') {
  for (const q of bank.questions) {
    try { J.normalizeAnswer(q); normalized++; } catch (e) { bad++; }
  }
  out.push('题库全量 normalizeAnswer: 成功 ' + normalized + ' / 失败 ' + bad);
}

// 首页渲染尝试
let rendered = false;
try {
  if (J && typeof J.render === 'function') { J.render(); rendered = true; }
} catch (e) { out.push('render 抛错: ' + String(e)); }
out.push('render() 可调用: ' + (rendered ? 'YES' : '未暴露(跳过)'));

console.log(out.join('\n'));
if (!loaded) process.exit(2);
"""

if __name__ == "__main__":
    sys.exit(main())
