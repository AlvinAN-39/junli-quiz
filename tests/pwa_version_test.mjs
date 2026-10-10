/**
 * tests/pwa_version_test.mjs — PWA 离线更新机制的静态契约验收
 * ===========================================================
 *
 * 背景（2026-10-09 修掉的真实故障：**联网看到新版本、断网重开仍是旧版本**）
 * 根因有两处，都在 app/sw.js：
 *   ① **缓存键不一致**：联网写入时用导航请求的 URL（如 `/`），断网回退却查 `./index.html`。
 *      Cache Storage 以请求 URL 为键，两者不是同一条目 → 断网时拿到的是另一份（往往是旧的）。
 *   ② **缓存名写死** `jlx-cache-v2`：sw.js 字节不随内容变化 → 浏览器不认为 Worker 有更新
 *      →  instal 不执行 → 旧 HTML 永远留在缓存里。修法是构建时把内容哈希注入进来。
 *
 * 本套件**只读源码与现有产物**，纯 Node 标准库，不依赖 dist/、build/、qa/ 或网络，
 * 因此 clone 下来即可运行、可以进 CI：
 *   · 第 1 组：直接读 app/sw.js 与 tools/bundle.py 做静态契约检查（最稳，必须做）；
 *   · 第 2 组：若 dist/web/sw.js 存在则校验产物；不存在则打印 SKIP 跳过（不算失败）。
 *
 * 与 `qa-env/pwa_version_e2e.mjs` 的分工（两者互补，不要混淆）：
 *   那份用 Playwright 起**真实浏览器**，跑「部署版本 A → 换成 B → 断网重载必须是 B」的
 *   跨版本端到端场景，并带 `JLX_LEGACY=1` 自检（模拟旧实现必须失败）；
 *   它依赖项目外的 qa-env 环境，只在本地跑。本套件负责 CI 能跑的静态契约。
 *
 * 用法：node tests/pwa_version_test.mjs
 * 输出：每项一行 [PASS]/[FAIL]/[SKIP]，末尾一行 JSON 摘要（便于 CI 归档）。
 * 退出码：全部通过 0；存在失败非 0（SKIP 不算失败）。
 */

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');

const SW = path.join(ROOT, 'app', 'sw.js');
const BUNDLE = path.join(ROOT, 'tools', 'bundle.py');
const DIST_SW = path.join(ROOT, 'dist', 'web', 'sw.js');

const checks = [];
let pass = 0, fail = 0, skip = 0;

function check(name, ok, detail = '') {
  checks.push({ name, ok: !!ok, detail: String(detail) });
  if (ok) { pass++; console.log(`[PASS] ${name}${detail ? ' — ' + detail : ''}`); }
  else { fail++; console.log(`[FAIL] ${name}${detail ? ' — ' + detail : ''}`); }
}
function skipped(name, detail = '') {
  checks.push({ name, ok: true, skipped: true, detail: String(detail) });
  skip++;
  console.log(`[SKIP] ${name}${detail ? ' — ' + detail : ''}`);
}

/** 取 `var NAME = ['a','b'];` 形式的数组字面量里的字符串项（用于精确检查预缓存清单） */
function arrayItems(src, name) {
  const m = src.match(new RegExp(`var\\s+${name}\\s*=\\s*\\[([\\s\\S]*?)\\]\\s*;`));
  if (!m) return null;
  return [...m[1].matchAll(/'([^']*)'/g)].map((x) => x[1]);
}

/** 从 marker 起做**大括号配对**，取出那一整段代码块（用于只看导航分支，不被其它分支干扰） */
function braceBlock(src, marker) {
  const i = src.indexOf(marker);
  if (i < 0) return null;
  const open = src.indexOf('{', i);
  if (open < 0) return null;
  let depth = 0;
  for (let j = open; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(open, j + 1); }
  }
  return null;
}

/** 复刻 tools/bundle.py 的 content_hash：sha256(文件名字节 + 内容字节) 取前 12 位 */
function contentHash(files) {
  const h = crypto.createHash('sha256');
  for (const f of files) {
    h.update(path.basename(f));          // 对应 Python 的 p.name.encode("utf-8")
    h.update(fs.readFileSync(f));        // 对应 p.read_bytes()
  }
  return h.digest('hex').slice(0, 12);
}

/* ==========================================================================
 * 第 1 组：静态契约（直接读源码）
 * ======================================================================== */
if (!fs.existsSync(SW)) {
  console.log('[FAIL] 找不到 app/sw.js —— 静态契约无法检查');
  process.exit(1);
}
const sw = fs.readFileSync(SW, 'utf8');
const bundle = fs.existsSync(BUNDLE) ? fs.readFileSync(BUNDLE, 'utf8') : '';

// ① HTML_KEY 常量存在
const htmlKey = sw.match(/var\s+HTML_KEY\s*=\s*'([^']+)'/);
check('app/sw.js 定义了 HTML_KEY 常量', !!htmlKey, htmlKey ? `HTML_KEY = ${htmlKey[1]}` : '未找到');

// ② 联网写入用 HTML_KEY（而不是请求 URL）——旧实现正是在导航分支里写 cachePut(req, …)。
//    ⚠ 必须**只检查导航分支**：sw.js 自身那个分支用 cachePut(req, …) 是正确且必要的
//    （脚本就是要按自己的 URL 存一份，否则断网刷新校验 sw.js 会失败、整个 SW 失效）。
//    早期版本这里全文件搜 `cachePut(req,`，把那个合法分支误判成了缺陷。
const navBlock = braceBlock(sw, "if (req.mode === 'navigate')");
const writeUsesKey = !!navBlock && /cachePut\(HTML_KEY\s*,/.test(navBlock);
const legacyWrite = !!navBlock && /cachePut\(req\s*,/.test(navBlock);
check('导航写入使用 HTML_KEY（不再用请求 URL 作键）',
  !!navBlock && writeUsesKey && !legacyWrite,
  !navBlock ? "未找到导航分支 if (req.mode === 'navigate')"
    : legacyWrite ? '导航分支仍在用 cachePut(req, …) 作键'
    : writeUsesKey ? '导航分支 cachePut(HTML_KEY, …)' : '导航分支未用 HTML_KEY 写入');

// ③ 断网回退用同一个键（matchHtml() 里必须是 caches.match(HTML_KEY)）
const matchHtmlBody = sw.match(/function\s+matchHtml\s*\([^)]*\)\s*\{([\s\S]*?)\}/);
const readUsesKey = !!(matchHtmlBody && /caches\.match\(HTML_KEY\)/.test(matchHtmlBody[1]));
check('断网回退使用同一个 HTML_KEY', readUsesKey,
  readUsesKey ? 'caches.match(HTML_KEY)' : '回退未使用 HTML_KEY');

// ④ 旧实现的「再回退到根路径 ./」必须消失 —— 那正是断网拿到旧 HTML 的路径
const legacyFallback = /caches\.match\('\.\/'\)/.test(sw);
check("不再存在回退到根路径键 caches.match('./') 的旧写法", !legacyFallback,
  legacyFallback ? '仍会回退到 ./' : '已移除');

// ⑤ 同一个键至少被引用两次（写入 + 回退各一处），交叉印证 ②③
const keyRefs = (sw.match(/HTML_KEY/g) || []).length;
check('HTML_KEY 在写入与回退两处均被引用', keyRefs >= 2, `引用 ${keyRefs} 次`);

// ⑥ CACHE_NAME 由 BUILD_ID 拼接
const cacheNameOk = /var\s+CACHE_NAME\s*=\s*'jlx-cache-'\s*\+\s*BUILD_ID/.test(sw);
check('CACHE_NAME 由 BUILD_ID 拼接（缓存名随内容变化）', cacheNameOk,
  cacheNameOk ? "CACHE_NAME = 'jlx-cache-' + BUILD_ID" : '未按 BUILD_ID 拼接');

// ⑥b activate 只能清理**本应用前缀**的缓存
//    Cache Storage 按 origin 共享、不按 scope 隔离：删掉所有非当前名的缓存
//    会连带清空同源下其它应用的离线缓存。
const prefixDecl = /var\s+CACHE_PREFIX\s*=\s*'jlx-cache-'/.test(sw);
const actStart = sw.indexOf("addEventListener('activate'");
const fetchStart = sw.indexOf("addEventListener('fetch'");
const activateBlock = (actStart >= 0 && fetchStart > actStart) ? sw.slice(actStart, fetchStart) : '';
const scopedDelete = /indexOf\(CACHE_PREFIX\)\s*===\s*0/.test(activateBlock);
check('activate 只清理本应用前缀的缓存（不误删同源其它应用）', prefixDecl && scopedDelete,
  `CACHE_PREFIX=${prefixDecl} scopedDelete=${scopedDelete}`);

// ⑥c 提纲数据走网络优先（支持「不重新打包、直接替换部署目录文件」的方式二）
const outlineNetFirst = /outline-2026\.json/.test(sw) &&
  /outline-2026\.json[\s\S]{0,600}?fetch\(req\)/.test(sw);
check('提纲数据走网络优先（换文件后能更新）', outlineNetFirst,
  outlineNetFirst ? '网络优先 + 断网回退缓存' : '仍走缓存优先，换提纲不会生效');

// ⑦ 源码里保留 __BUILD_ID__ 占位符（由构建注入）
check('app/sw.js 保留 __BUILD_ID__ 占位符', sw.includes('__BUILD_ID__'),
  sw.includes('__BUILD_ID__') ? '占位符在' : '占位符缺失，构建将无法注入标识');

// ⑧ tools/bundle.py：替换 + 校验残留 + 缺占位符报错
check('bundle.py 会替换 __BUILD_ID__ 占位符',
  /replace\(\s*"__BUILD_ID__"\s*,\s*stamp\s*\)/.test(bundle), '');
const residualGuard = /if\s+"__BUILD_ID__"\s+in\s+out\s*:/.test(bundle);
check('bundle.py 替换后校验残留（残留即报错终止）', residualGuard,
  residualGuard ? '有残留校验' : '缺少残留校验——会把 jlx-cache-__BUILD_ID__ 发到线上');
const missingGuard = /if\s+"__BUILD_ID__"\s+not\s+in\s+src\s*:/.test(bundle);
check('bundle.py 在源码缺占位符时报错终止', missingGuard,
  missingGuard ? '有缺失校验' : '缺少缺失校验');

// ⑨ 预缓存清单不再包含已被内联的文件（必须精确解析数组，不能整文件 grep —— 注释里也提到这些名字）
const critical = arrayItems(sw, 'CRITICAL');
const optional = arrayItems(sw, 'OPTIONAL');
const precache = [...(critical || []), ...(optional || [])];
const INLINED = ['app.js', 'app.css', 'questions.json'];
const leaked = precache.filter((u) => INLINED.some((f) => u.endsWith(f)));
check('预缓存列表不再包含 app.js / app.css / data/questions.json（已内联）',
  !!critical && leaked.length === 0,
  `CRITICAL=[${(critical || []).join(', ')}] OPTIONAL=[${(optional || []).join(', ')}]` +
  (leaked.length ? ` 泄漏=${leaked.join(', ')}` : ''));

// ⑩ cache-status 消息接口（供设置页显示「离线版本」）
const hasMessage = /self\.addEventListener\('message'/.test(sw);
const hasStatusType = sw.includes("'cache-status'");
const statusFields = ['cacheName', 'buildId', 'hasHtml'].filter((f) => new RegExp(f + '\\s*:').test(sw));
check('存在 cache-status 消息接口且回传 cacheName / buildId / hasHtml',
  hasMessage && hasStatusType && statusFields.length === 3,
  `message=${hasMessage} type=${hasStatusType} 字段=[${statusFields.join(', ')}]`);

/* ==========================================================================
 * 第 2 组：构建产物（存在才检查）
 * ======================================================================== */
if (!fs.existsSync(DIST_SW)) {
  skipped('构建产物校验（dist/web/sw.js）', '产物不存在，跳过；先跑 python tools/bundle.py 可启用');
} else {
  const dist = fs.readFileSync(DIST_SW, 'utf8');

  const leftovers = (dist.match(/__BUILD_ID__/g) || []).length;
  check('产物 sw.js 中 __BUILD_ID__ 残留为 0', leftovers === 0, `残留 ${leftovers} 处`);

  const idMatch = dist.match(/var\s+BUILD_ID\s*=\s*'([0-9a-f]{12})'/);
  check('产物 sw.js 的 BUILD_ID 是 12 位十六进制', !!idMatch, idMatch ? idMatch[1] : '未匹配到 12 位十六进制标识');

  const cacheNameMatch = dist.match(/var\s+CACHE_NAME\s*=\s*'jlx-cache-'\s*\+\s*BUILD_ID/);
  check('产物 sw.js 的 CACHE_NAME 形如 jlx-cache-<12 位十六进制>',
    !!cacheNameMatch && !!idMatch, idMatch ? `jlx-cache-${idMatch[1]}` : '');

  // 稳定性：按 bundle.py 的算法**静态重算**内容哈希，与产物里注入的标识比对。
  //   重算输入必须与 tools/bundle.py 的 render_sw 完全一致：**源码文件**，不含 dist 产物。
  //   这同时是「构建时间戳没被算进哈希」的守卫 —— 若 bundle.py 改回用 dist/web/index.html
  //   （它内嵌 window.__BUILD__，含打包时刻），重算结果就与产物标识对不上，本项立刻失败。
  //   内容未变 → 标识必然一致；这正是「同一份源码重复构建标识稳定」的等价验证。
  const hashInputs = [
    path.join(ROOT, 'app', 'index.html'),
    path.join(ROOT, 'app', 'app.css'),
    path.join(ROOT, 'app', 'app.js'),
    path.join(ROOT, 'data', 'questions.json'),
    path.join(ROOT, 'app', 'manifest.webmanifest'),
    path.join(ROOT, 'app', 'icons', 'icon.svg')
  ];
  // 与构建器一致：本地有提纲时，它也是内联内容的一部分。
  const outlineInput = path.join(ROOT, 'data', 'outline-2026.json');
  if (fs.existsSync(outlineInput)) hashInputs.push(outlineInput);
  const missing = hashInputs.filter((f) => !fs.existsSync(f));
  if (missing.length) {
    skipped('构建标识稳定性（内容未变则标识不变）', '缺少输入文件：' + missing.map((f) => path.relative(ROOT, f)).join(', '));
  } else {
    const recomputed = contentHash(hashInputs);
    check('构建标识 = 当前内容的哈希（同一份内容重复构建标识稳定）',
      recomputed === (idMatch ? idMatch[1] : null),
      `重算 ${recomputed} / 产物 ${idMatch ? idMatch[1] : '-'}`);
  }
}

/* ==========================================================================
 * 汇总
 * ======================================================================== */
console.log('');
console.log(JSON.stringify({ suite: 'pwa_version', pass, fail, skip, checks }));
console.log(`PWA 离线更新契约：通过 ${pass}，失败 ${fail}，跳过 ${skip}`);
process.exit(fail === 0 ? 0 : 1);
