#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bundle.py — 把 app/ + data/questions.json 组装成可交付产物
=========================================================

产出（写入 dist/）：
  1. `dist/军理刷题.html`  ★ 单文件离线版
     内联 app.css + app.js + 题库 JSON，**零外部请求**。
     双击即可用；拷到 iPhone「文件」App 后用 Safari 打开也能用。
  2. `dist/web/index.html` + `app.css` + `app.js` + `data/questions.json`
     + `manifest.webmanifest` + `sw.js` + `icons/icon.svg`
     → PWA 版，可「添加到主屏幕 / 安装为应用」，Service Worker 真正离线。
     （sw.js 的 scope 限制要求 index.html 与 data/ 同层，故放同一目录）

内联注意事项（来自交付说明）：
  * app.js 是单个 IIFE 普通脚本，无 `import`/`export`，可安全字符串内联。
  * app.js 内不含 `</script>`，但仍做一次防御性替换（`</` → `<\\/`）。
  * 单文件版**不加**静态 `<link rel="manifest">`（file:// 下会触发 CORS 报错），
    App 自身会在 http/https 下动态注入。
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
DATA = ROOT / "data" / "questions.json"
DIST = ROOT / "dist"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 参考书目（Reference）
# ---------------------------------------------------------------------------
# 本软件是围绕一本指定教材建设的，因此必须在软件内给出明确书目与用途说明。
# 书目信息核对来源见 docs/03-reference.md。
REFERENCE = {
    "authors": "徐亮、李隽隽、刘捷",
    "title": "普通高校军事课教程",
    "press": "中山大学出版社",
    "edition": "2023 年 8 月第 1 版",
    "isbn": "978-7-306-07893-3",
    "note": "图书版权页 版权页另注明「2026 年 5 月第 4 次印刷」",
    "use": [
        "题库章节框架与教材五章完全对应（中国国防 / 国家安全 / 军事思想 / 现代战争 / 信息化装备）。",
        "教材全文（约 20.5 万中文字）作为独立语料，用于核校题目选项表述是否规范。",
        "题库答案已逐题比对教材原文、历年真题与模拟题库；与教材冲突者已按教材更正并注明依据。",
    ],
}

REFERENCE_JS = r"""
/* ==========================================================================
 * 参考书目卡片（由 tools/bundle.py 在打包时注入）
 * --------------------------------------------------------------------------
 * 为什么用注入而不是改 app.js：
 *   app.js 已验收冻结（浏览器 E2E 34/34），这里只做**只读增强**——
 *   在首页视图末尾追加一张书目卡片，不触碰任何既有逻辑、不新增存储键。
 * 幂等性：MutationObserver 在有卡片时立即返回，不产生新的 DOM 变更，不会自激。
 * ========================================================================== */
(function () {
  'use strict';
  var REF = __REFERENCE_JSON__;

  var LOGO = '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" '
    + 'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
    + 'stroke-linejoin="round"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H19v15H6.5A2.5 2.5 0 0 0 '
    + '4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H19v3H6.5A2.5 2.5 0 0 1 4 20.5z"/>'
    + '<path d="M8 7.5h7M8 10.5h5"/></svg>';

  function card() {
    var items = '<li>' + REF.use.join('</li><li>') + '</li>';
    return ''
      + '<div class="card" id="ref-book-card" style="margin-top:14px">'
      + '  <div class="card-title" style="display:flex;align-items:center;gap:9px">'
      + '    <span style="flex:0 0 auto;display:inline-flex;color:var(--primary)">' + LOGO + '</span>'
      + '    <span>参考书目</span>'
      + '    <span class="card-sub" style="margin-left:auto;font-weight:500">题库的依据</span>'
      + '  </div>'
      + '  <div style="font-size:.95em;line-height:1.75">'
      + '    <div><b>' + REF.authors + ' 主编</b>：《' + REF.title + '》，'
      + REF.press + '，' + REF.edition + '。</div>'
      + '    <div class="muted small" style="margin-top:4px">ISBN ' + REF.isbn
      + '　·　' + REF.note + '</div>'
      + '  </div>'
      + '  <div class="note" style="margin-top:10px">'
      + '    <div style="font-weight:600;margin-bottom:4px">本书在本软件中的作用</div>'
      + '    <ul style="margin:0;padding-left:1.15em;line-height:1.7">' + items + '</ul>'
      + '  </div>'
      + '  <div class="note small" style="margin-top:10px">'
      + '    教材著作权归 ' + REF.authors + ' 及' + REF.press + '所有。'
      + '本软件为个人学习复习工具，打包产物中不含教材正文，仅含结构化题目。'
      + '  </div>'
      + '</div>';
  }

  var aboutReady = false;
  function boot() {
    if (aboutReady) return;
    var view = document.getElementById('view');
    if (!view) return;
    aboutReady = true;

    function tryInject() {
      var v = document.getElementById('view');
      if (!v || v.querySelector('#ref-book-card')) return;
      // 只在首页（题库总览）追加，避免污染练习/考试界面
      if (!/题库总览|继续上次练习|从第一题开始/.test(v.textContent || '')) return;
      var old = v.querySelector('#ref-book-card');
      if (old) old.parentNode.removeChild(old);
      v.insertAdjacentHTML('beforeend', card());
    }

    try { tryInject(); } catch (e) { /* noop */ }
    try {
      var mo = new MutationObserver(function () {
        // 有卡片就什么都不做，避免观察器自激
        var v = document.getElementById('view');
        if (!v || v.querySelector('#ref-book-card')) return;
        tryInject();
      });
      mo.observe(document.getElementById('view'), { childList: true, subtree: true });
    } catch (e) { /* noop */ }
    window.addEventListener('hashchange', function () {
      setTimeout(function () { try { tryInject(); } catch (e) { /* noop */ } }, 0);
    }, false);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, false);
  } else {
    boot();
  }
})();
"""


def reference_script() -> str:
    """生成注入用的 <script>（JSON 内联，避免手工转义引号）。"""
    payload = json.dumps(REFERENCE, ensure_ascii=False)
    return REFERENCE_JS.replace("__REFERENCE_JSON__", payload)


def safe_inline(js: str) -> str:
    """防止 `</script>` 提前闭合 script 标签。"""
    return js.replace("</script", "<\\/script").replace("<!--", "<\\!--")


def strip_debug_fields(bank: dict) -> tuple[dict, dict]:
    """从打包用的题库里去掉**前端零读取**的字段（绝不删用于渲染的内容）。

    依据：对 `app/app.js` 逐字段统计属性访问（`.字段名`）得到的生产侧证据，
    零引用者才允许删除；保留原因写在每条后面。

    * `raw`（0 次引用）—— 契约已注明「调试用，不进 dist」。实测占 7.4%。
    * `webSourceUrl`（0 次引用）—— 联网核查的原始链接，前端不显示。
    * `relatedSection`（0 次引用）—— 语料定位信息，前端不显示。
    * `lawCitationIssue` / `lawCitationStatus`（各 0 次引用）—— 法条复核标记，
      前端不显示；结论文字已写在 `explanation` / `note` 里，不丢信息。
    * `answerUncertain`（前端仅 `q.answerUncertain === true` 一处判定，全库均为
      false）—— 原「多选答案切分存疑」标记，已随复核解除，删除后界面不变。
    * `explanationParts.ref` —— 与顶层 `explanationRef` 逐字重复，
      前端 `explainSrcLine()` 取 `q.explanationRef || parts.ref`，删掉零影响。

    **不删** `explanationParts.reason`：虽然它与 `explanation` 里那句话重复，
    但前端 `explainBody()` 正是靠它渲染出「为什么」这一行 ——
    删掉会让解析退化成只有「正确答案」一行，损失可读性。
    （实测踩过：删了之后界面上「为什么」行消失。）

    **不删** `explanationSrc` / `explanationRef` / `source` / `section`：
    分别被 `explainSrcLine()`、搜索结果列表读取。
    """
    removed = {"raw": 0, "webSourceUrl": 0, "relatedSection": 0,
               "lawCitationIssue": 0, "lawCitationStatus": 0,
               "answerUncertain": 0, "parts.ref": 0}
    for q in bank.get("questions", []):
        for field in ("raw", "webSourceUrl", "relatedSection",
                      "lawCitationIssue", "lawCitationStatus", "answerUncertain"):
            if q.pop(field, None) is not None:
                removed[field] += 1
        parts = q.get("explanationParts")
        if isinstance(parts, dict) and parts.get("ref") == q.get("explanationRef"):
            parts.pop("ref", None)
            removed["parts.ref"] += 1
    return bank, removed


def build_stamp() -> dict:
    """构建版本号：**日期+时间**（用户要求首页左上角以此标注版本）。

    形如 `2026.09.30-1616`；同时给出 ISO 串便于排查。
    以打包时刻为准 —— 每次重新打包都会刷新，用户一眼就能看出手上是哪一版。
    """
    now = datetime.now()
    return {"v": now.strftime("%Y.%m.%d-%H%M"),
            "iso": now.strftime("%Y-%m-%dT%H:%M:%S")}


def build_single_file(bank: dict) -> Path:
    bank, removed = strip_debug_fields(bank)
    print("   字段精简：" + "、".join("%s×%d" % (k, v) for k, v in removed.items() if v))
    html = read(APP / "index.html")
    css = read(APP / "app.css")
    js = read(APP / "app.js")
    bank_json = json.dumps(bank, ensure_ascii=False, separators=(",", ":"))
    stamp = build_stamp()

    # 1) 去掉外部样式表引用，换成内联
    html = re.sub(r'\s*<link[^>]*rel=["\']stylesheet["\'][^>]*>', "", html)
    html = html.replace("</head>", f"<style>\n{css}\n</style>\n</head>", 1)

    # 2) 题库注入 + 脚本内联（放在 </body> 前，保证 DOM 已就绪）
    #    注意：构建版本号必须放在**独立的 <script>** 里 ——
    #    与题库写在同一个 <script> 中会让「提取题库 JSON」的检查(verify_app.py)
    #    读到紧随其后的 `window.__BUILD__ = …`，报 "Extra data" 解析失败（实测踩过）。
    inject = (
        "<script>\n"
        f"window.__QUESTION_BANK__ = {bank_json};\n"
        "</script>\n"
        "<script>\n"
        f"window.__BUILD__ = {json.dumps(stamp, ensure_ascii=False)};\n"
        "</script>\n"
        "<script>\n"
        f"{safe_inline(js)}\n"
        "</script>\n"
        "<script>\n"
        f"{safe_inline(reference_script())}\n"
        "</script>\n"
        "</body>"
    )
    html = re.sub(r'\s*<script[^>]*src=["\'][^"\']*["\'][^>]*>\s*</script>', "", html)
    html = html.replace("</body>", inject, 1)

    out = DIST / "军理刷题.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def build_web(bank: dict) -> Path:
    """PWA 版：**在单文件版基础上**加静态 manifest + SW 注册。

    关键设计：PWA 版也把题库**内嵌**进 index.html。
    原因：`dist/web/index.html` 是用户很容易直接双击的文件；若题库只放在
    `data/questions.json`，`file://` 下 fetch 被拦 → App 静默退化为 16 题 mock 题库，
    看起来就像「题库没内嵌」。内嵌后无论双击还是走 HTTP 都能拿到 1171 题；
    同时仍保留 `data/questions.json`（供 PWA 缓存与外部工具核对）。
    """
    web = DIST / "web"
    if web.exists():
        shutil.rmtree(web)
    (web / "data").mkdir(parents=True, exist_ok=True)
    (web / "icons").mkdir(parents=True, exist_ok=True)

    # 以单文件版为基底（CSS/JS/题库已全部内联）
    single = DIST / "军理刷题.html"
    if not single.exists():
        build_single_file(bank)
    html = read(single).replace("</body>", "</body>", 1)

    # 1) 补上静态 manifest（HTTP 下无 CORS 问题）
    html = html.replace(
        "</head>", '  <link rel="manifest" href="manifest.webmanifest">\n</head>', 1)
    # 2) 注册 Service Worker（仅 http/https）
    html = html.replace(
        "</body>",
        "<script>\n"
        "  if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {\n"
        "    addEventListener('load', function () {\n"
        "      navigator.serviceWorker.register('sw.js').catch(function () {});\n"
        "    });\n"
        "  }\n"
        "</script>\n</body>", 1)
    (web / "index.html").write_text(html, encoding="utf-8")

    for name in ("app.css", "app.js", "sw.js", "manifest.webmanifest"):
        shutil.copy2(APP / name, web / name)
    shutil.copy2(APP / "icons" / "icon.svg", web / "icons" / "icon.svg")
    # PWA 的 data/questions.json 只作「外部核对 / SW 预缓存」用，App 一律优先读内嵌题库，
    # 因此这里同样做字段精简 —— 否则会白占 SW 缓存与部署包体积（实测该文件 2.0 MB）。
    lean, _removed = strip_debug_fields(bank)
    (web / "data" / "questions.json").write_text(
        json.dumps(lean, ensure_ascii=False, indent=1), encoding="utf-8")
    return web / "index.html"


def main() -> int:
    if not DATA.exists():
        print(f"缺少题库文件：{DATA}", file=sys.stderr)
        return 1
    bank = json.loads(DATA.read_text(encoding="utf-8"))
    n = len(bank.get("questions", []))
    single = build_single_file(bank)
    index = build_web(bank)

    # 体检：单文件版不得有外部请求
    html = read(single)
    externals = re.findall(r'(?:src|href)\s*=\s*["\'](https?:)?//[^"\']+', html)
    fetch_calls = re.findall(r"fetch\s*\(", read(APP / "app.js"))

    print("=" * 70)
    print("构建完成（单文件离线版 + PWA 版）")
    print("=" * 70)
    print(f"题库: {n} 题  counts={bank.get('counts')}")
    print(f"  1) {single}")
    print(f"     大小 {single.stat().st_size / 1024:.0f} KB  题库已内嵌")
    print(f"  2) {index}")
    print(f"     大小 {(index.parent / 'index.html').stat().st_size / 1024:.0f} KB"
          f"（题库已内嵌） + data/questions.json "
          f"{(index.parent / 'data' / 'questions.json').stat().st_size / 1024:.0f} KB（备用/供 SW 缓存）")
    print(f"外部资源引用: {len(externals)}（应为 0）{externals[:3]}")
    print(f"app.js 中 fetch 出现次数: {len(fetch_calls)}")
    print(f"内联脚本数: {html.count('<script')}")
    print(f"内联样式数: {html.count('<style')}")
    print(f"题库已内联: {'window.__QUESTION_BANK__' in html}")
    web_html = read(index)
    print(f"PWA 版题库亦已内联: {'window.__QUESTION_BANK__' in web_html}"
          f"  (静态 manifest: {'manifest.webmanifest' in web_html},"
          f" SW 注册: {'serviceWorker' in web_html})")
    print(f"参考书目卡片已注入: {'ref-book-card' in html}  "
          f"({REFERENCE['authors']}《{REFERENCE['title']}》ISBN {REFERENCE['isbn']})")

    # 3) 一键部署包：把 dist/web 打成单个 zip，方便「拖进去就发布」
    zip_path = build_deploy_zip()
    print(f"一键部署包: {zip_path}  ({zip_path.stat().st_size / 1024:.0f} KB)")
    return 0


def build_deploy_zip() -> Path:
    """把 `dist/web/` 打成 `dist/军理刷题-网页版.zip`。

    用途：让**没有电脑**的用户也能在 iPhone 上把 App 发布到一个永久网址——
    在手机浏览器里打开免费静态托管（如 Netlify Drop），选这个 zip 上传即可。
    zip 内部是**扁平结构**（index.html 在根目录），符合拖拽部署平台的要求。
    """
    import zipfile

    web = DIST / "web"
    out = DIST / "军理刷题-网页版.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(web.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(web).as_posix())
    return out
    print(f"生成时间: {datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
