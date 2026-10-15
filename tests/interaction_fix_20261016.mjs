/**
 * tests/interaction_fix_20261016.mjs — 2026-10-16 交互修复批次（7 组 / 9 项）回归套件
 * =============================================================================
 *
 * **这是长期保留的回归资产，不是一次性探针。** 每一项都对应一条具体的用户可见回归，
 * 删掉它等于删掉该场景唯一的代码化验证。逐项「要防的回归」写在各自的注释里。
 *
 * 覆盖：
 *   · 清空本机数据后错题徽章与统计必须归零（防止 reset 只清了数据、没失效统计缓存）；
 *   · 手机端顶栏返回箭头必须真的回到首页（练习设置页 / 练习答题页 / 背题页三个入口）；
 *   · 答题卡按钮必须自述展开状态（textContent + aria-expanded + .qgrid 三者一致）；
 *   · 模拟考试组卷不得出现同题干、同知识点的重复题（连续 5 轮抽样验证）；
 *   · 错题本按章节分组（章节卡片数量 = 实际出现的章节数，点进去只列该章题目）；
 *   · 背题过程中可切换章节（无需退出重进，切换后当前背的就是该章题目）；
 *   · 待复习练习入口（按钮文案含待复习题数，进入后题目集合与顺序都对）。
 *
 * 环境自适应（CI 里没有浏览器，必须保持全绿）：
 *   · Playwright 探测顺序：`JLX_PLAYWRIGHT` → 项目 `node_modules/playwright`
 *     → 同级 `../qa-env/node_modules/playwright`；全部没有则打印 SKIP 并以退出码 0 结束；
 *   · 产物 `dist/军理刷题.html` 不存在（CI 的 tests 作业不构建）同样 SKIP、退出码 0。
 *   · 注意：SKIP 只针对「不可运行」，**不针对「产物落后于 app/app.js」**。产物里的功能没落地时
 *     这里是真失败（非 0 退出），因为套件就是用来发现这类问题的。
 *
 * 手机场景：用 Playwright 的 `devices['iPhone 15']` 建立带 `hasTouch` 的上下文，
 * 返回按钮用真实触摸 `page.tap('#btn-back')` —— 鼠标 click 不覆盖移动端触摸路径。
 *
 * 夹具注入注意：**不要**「先进页面 → 改 localStorage → 改 hash 跳转」，应用离开路由时
 * 会把内存会话写回存档、覆盖夹具。本文件一律「改 localStorage → page.reload()」，
 * 让应用自己从磁盘读夹具。
 *
 * 用法（与其它套件一致，从 qa-env 目录运行）：
 *   cd ../qa-env && node ../军理刷题/tests/interaction_fix_20261016.mjs
 *   或在本项目目录：node tests/interaction_fix_20261016.mjs
 * 输出：每项一行 [PASS]/[FAIL]，末尾一行 JSON 摘要。
 * 退出码：全部通过 0；存在失败或页面报错非 0（SKIP 不算失败）。
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const DIST = path.join(ROOT, 'dist', '军理刷题.html');
const URL = pathToFileURL(DIST).href;

/** 进度、设置、考试存档、meta 四个 localStorage 键（与 app/app.js 的常量同名同值）。 */
const KEY_PROGRESS = 'jlx.progress.v1';
const KEY_SETTINGS = 'jlx.settings.v1';
const KEY_EXAM = 'jlx.exam-session.v1';
const KEY_META = 'jlx.meta.v1';

/**
 * 探测可用的 Playwright。入库版本不能写本机绝对路径，因此按候选顺序尝试；
 * 全部失败返回 null，由调用处打印 SKIP（CI 属正常情况，不算失败）。
 * 同时取回 `devices` —— 它是 playwright 模块的具名导出，**不在 chromium 上**
 * （`chromium.devices` 为 undefined，手机场景曾因此整批报错）。
 */
async function loadPlaywright() {
  const candidates = [
    process.env.JLX_PLAYWRIGHT,
    path.join(HERE, '..', 'node_modules', 'playwright', 'index.mjs'),
    path.join(HERE, '..', '..', 'qa-env', 'node_modules', 'playwright', 'index.mjs'),
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      const mod = await import(pathToFileURL(candidate).href);
      if (mod.chromium) return { chromium: mod.chromium, devices: mod.devices || {} };
    } catch { /* 该候选不可用，继续尝试下一个 */ }
  }
  return null;
}

const results = [];
const errors = [];
let pass = 0;
let fail = 0;

/** 环境不满足（无 Playwright 或无产物）时优雅退出：打印 SKIP 原因，退出码 0。 */
function skipAll(reason) {
  console.log(`[SKIP] 2026-10-16 交互修复回归（7 组 / 9 项） — ${reason}`);
  console.log(JSON.stringify({ suite: 'interaction_fix_20261016', checks: 0, pass: 0, fail: 0,
    skip: 1, reason, skipped: true }, null, 2));
  process.exit(0);
}

const playwright = await loadPlaywright();
if (!playwright) {
  skipAll('未找到 Playwright（可设置 JLX_PLAYWRIGHT，或在同级 qa-env 安装 playwright）');
}
const { chromium, devices } = playwright;
if (!fs.existsSync(DIST)) {
  skipAll(`未找到产物 ${path.relative(ROOT, DIST)}（先运行 python tools/bundle.py）`);
}

const browser = await chromium.launch();
let context;
let page;

function assert(value, message) {
  if (!value) throw new Error(message);
}

/** 每项失败单独记录，后续场景继续运行；逐项输出，末尾给 JSON 摘要。 */
async function scenario(name, task) {
  try {
    await task();
    results.push({ name, ok: true });
    pass++;
    console.log(`[PASS] ${name}`);
  } catch (error) {
    const detail = String((error && error.message) || error).slice(0, 600);
    results.push({ name, ok: false, error: detail });
    fail++;
    console.log(`[FAIL] ${name} — ${detail}`);
  }
}

function watch(target) {
  target.setDefaultTimeout(5000);
  target.on('pageerror', (error) => errors.push(String(error)));
  target.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
}

/** 关掉开屏公告：它盖在整个界面上，不关掉后面所有点击都会被拦截。 */
async function dismissNotice() {
  const notice = page.locator('#modal-foot button').filter({ hasText: /^知道了$/ });
  if (await notice.count() && await notice.first().isVisible()) await notice.first().click();
}

async function ready() {
  await page.waitForFunction(() => window.__JLX__?.state.questions.length > 0
    && document.querySelector('#view')?.textContent?.trim(), null, { timeout: 20000 });
  // 公告延迟 260ms 出现，必须等它的窗口结束后再关闭。
  await page.waitForTimeout(450);
  await dismissNotice();
}

/**
 * 新建上下文并首次加载。
 * mobile=true 时使用 iPhone 15 设备描述（含 hasTouch），返回按钮要用真实触摸点击。
 */
async function fresh({ hash = '#/home', mobile = false, viewport = { width: 1280, height: 800 } } = {}) {
  if (context) await context.close();
  if (mobile) {
    const device = { ...(devices['iPhone 15'] || {}) };
    assert(device.hasTouch, '当前 Playwright 没有 iPhone 15 设备描述（无法模拟真实触摸）');
    context = await browser.newContext({ ...device, colorScheme: 'light' });
  } else {
    context = await browser.newContext({ viewport, colorScheme: 'light' });
  }
  page = await context.newPage();
  watch(page);
  await page.goto(`${URL}${hash}`, { waitUntil: 'load' });
  await ready();
  // 固定设置：关掉自动下一题/音效/震动，避免作答后被自动翻页或音频上下文报错干扰断言。
  await page.evaluate((key) => {
    const s = window.__JLX__.state.settings;
    localStorage.setItem(key, JSON.stringify({ ...s, autoNext: false, sound: false,
      haptic: false, theme: 'light' }));
  }, KEY_SETTINGS);
  await reload();
}

async function reload() {
  await page.reload({ waitUntil: 'load' });
  await ready();
}

/** 排除移动端隐藏侧栏等重复入口，只点击真正可见的元素。 */
async function click(selector) {
  const items = page.locator(selector);
  for (let i = 0, n = await items.count(); i < n; i++) {
    if (await items.nth(i).isVisible()) {
      await items.nth(i).click();
      return;
    }
  }
  throw new Error(`找不到可见入口：${selector}`);
}

/** 切页；应用偶发把点击当成「拖动手势」吞掉时重试一次，避免假失败。 */
async function nav(route) {
  await click(`[data-nav="${route}"]`);
  try {
    await page.waitForFunction((r) => window.__JLX__.state.route === r, route, { timeout: 2000 });
  } catch {
    await click(`[data-nav="${route}"]`);
    await page.waitForFunction((r) => window.__JLX__.state.route === r, route);
  }
}

/** 点确认弹窗里的指定按钮（按钮文案写在 #modal-foot 里）。 */
async function modal(label) {
  const button = page.locator('#modal-foot button').filter({ hasText: new RegExp(`^${label}$`) });
  if (!await button.count()) {
    const shown = await page.evaluate(() => document.querySelector('#modal-foot')?.textContent || '');
    throw new Error(`弹窗里没有「${label}」按钮，实际按钮文案：${shown}`);
  }
  await button.first().click();
}

async function stored(key) {
  return page.evaluate((k) => {
    const raw = localStorage.getItem(k);
    return raw ? JSON.parse(raw) : null;
  }, key);
}

/** 注入进度夹具后重新加载，让应用按生产启动路径读盘。 */
async function seedProgress(entries) {
  await page.evaluate(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)),
    { key: KEY_PROGRESS, value: entries });
  await reload();
}

/** 进度条目形状：与 app/app.js 的 ensureShape 输出字段一致。 */
function progress(overrides = {}) {
  return { seen: 0, correct: 0, wrong: 0, lastTs: 0, box: 0,
    fav: false, wrongFlag: false, ...overrides };
}

/** 题干归一化：去掉填空下划线（半角/全角）与空白，用于「同题干」判定。 */
function stemKey(text) {
  return String(text == null ? '' : text).replace(/[_＿\s]+/g, '');
}

function duplicateKeys(keys) {
  const seen = new Set();
  const dup = new Set();
  keys.forEach((k) => { if (seen.has(k)) dup.add(k); else seen.add(k); });
  return [...dup];
}

/** 直接读徽章文本并等它稳定（弹窗关闭、重绘都在同一帧内完成）。 */
async function badgeText(selector) {
  await page.waitForFunction((sel) => document.querySelector(sel)?.textContent != null, selector);
  return (await page.locator(selector).textContent()).trim();
}

/** 从真实题库里取两章各若干题，供跨章节夹具使用。 */
async function pickTwoChapters() {
  return page.evaluate(() => {
    const qs = window.__JLX__.state.questions;
    const chapters = [];
    qs.forEach((q) => { if (q.chapter && chapters.indexOf(q.chapter) < 0) chapters.push(q.chapter); });
    if (chapters.length < 2) throw new Error('真实题库章节少于 2 章，无法构造跨章节夹具');
    const idsOf = (c) => qs.filter((q) => q.chapter === c).map((q) => q.id);
    return { a: chapters[0], b: chapters[1], idsA: idsOf(chapters[0]), idsB: idsOf(chapters[1]) };
  });
}

try {
  /* ==========================================================================
   * 1. 清空本机数据后统计归零
   * 防的回归：重置只替换了 State.progress，却没有让派生统计缓存失效 ——
   *   数据没了、徽章和 __JLX__.derive() 还停在旧数字上（用户会以为没清干净）。
   * ======================================================================== */
  await scenario('1 清空本机数据后错题徽章与派生统计全部归零', async () => {
    await fresh();
    const ids = await page.evaluate(() => window.__JLX__.state.questions.slice(0, 3).map((q) => q.id));
    const seed = {};
    ids.forEach((id) => { seed[id] = progress({ seen: 1, wrong: 1, wrongFlag: true, lastTs: Date.now() }); });
    await seedProgress(seed);

    assert(await badgeText('#badge-wrong-t') === '3', `注入 3 条错题后移动端徽章应为 3，实际 ${await badgeText('#badge-wrong-t')}`);
    assert(await badgeText('#badge-wrong') === '3', `注入 3 条错题后侧栏徽章应为 3，实际 ${await badgeText('#badge-wrong')}`);
    const before = await page.evaluate(() => window.__JLX__.derive().wrong);
    assert(before === 3, `注入后 derive().wrong 应为 3，实际 ${before}`);

    await nav('sync');
    await click('[data-act="sync:reset"]');
    await modal('全部清空');

    assert(await badgeText('#badge-wrong-t') === '0', `清空后移动端徽章应为 0，实际 ${await badgeText('#badge-wrong-t')}`);
    assert(await badgeText('#badge-wrong') === '0', `清空后侧栏徽章应为 0，实际 ${await badgeText('#badge-wrong')}`);
    const cached = await page.evaluate(() => window.__JLX__.derive().wrong);
    const uncached = await page.evaluate(() => window.__JLX__.deriveUncached().wrong);
    assert(cached === 0, `清空后带缓存的 derive().wrong 应为 0，实际 ${cached}（统计缓存没有失效）`);
    assert(uncached === 0, `清空后 deriveUncached().wrong 应为 0，实际 ${uncached}`);
    const raw = await page.evaluate((k) => localStorage.getItem(k) || '', KEY_PROGRESS);
    assert(!raw.includes('wrongFlag'), `清空后进度存档里仍残留 wrongFlag：${raw.slice(0, 160)}`);
  });

  /* ==========================================================================
   * 2. 手机端返回箭头（iPhone 15 + 真实触摸）
   * 防的回归：顶栏返回按钮只绑了 click，移动端点不动；或点了不回到首页、
   *   顶栏标题与 location.hash 留在原页面（三个子场景各覆盖一个入口）。
   * ======================================================================== */

  /** 手机端公共断言：点返回后路由、标题、hash 三者必须一致地回到首页。 */
  async function assertBackToHome(from) {
    await page.tap('#btn-back');
    await page.waitForFunction(() => window.__JLX__.state.route === 'home');
    const title = (await page.locator('#page-title').textContent()).trim();
    assert(title === '首页', `${from} 点返回后标题应为「首页」，实际「${title}」`);
    const hash = await page.evaluate(() => window.location.hash);
    assert(hash === '#/home', `${from} 点返回后 hash 应为 #/home，实际 ${hash}`);
  }

  await scenario('2a 手机端练习设置页返回箭头回到首页', async () => {
    await fresh({ mobile: true, hash: '#/practice' });
    await page.waitForFunction(() => window.__JLX__.state.route === 'practice');
    assert(await page.locator('#btn-back').isVisible(), '练习设置页没有可见的返回箭头');
    await assertBackToHome('练习设置页');
  });

  await scenario('2b 手机端练习答题页返回箭头回到首页', async () => {
    await fresh({ mobile: true });
    await click('[data-act="home:startall"]');
    await page.waitForFunction(() => window.__JLX__.state.route === 'practice'
      && window.__JLX__.state.sess?.ids?.length > 0);
    await assertBackToHome('练习答题页');
  });

  await scenario('2c 手机端背题页返回箭头回到首页', async () => {
    await fresh({ mobile: true, hash: '#/recite' });
    await page.waitForFunction(() => window.__JLX__.state.route === 'recite');
    await click('[data-act="recite:start"]');
    await page.waitForFunction(() => window.__JLX__.state.sess?.mode === 'recite'
      && window.__JLX__.state.sess.ids.length > 0);
    await assertBackToHome('背题页');
  });

  /* ==========================================================================
   * 3. 答题卡按钮状态
   * 防的回归：按钮文案永远写死「答题卡」、也没有 aria-expanded，
   *   屏幕阅读器与用户都判断不出答题卡是展开还是收起。
   * ======================================================================== */
  await scenario('3 答题卡按钮文案与 aria-expanded 跟随展开状态', async () => {
    await fresh();
    await click('[data-act="home:startall"]');
    await page.waitForFunction(() => window.__JLX__.state.route === 'practice'
      && window.__JLX__.state.sess?.ids?.length > 0);
    const button = page.locator('[data-act="grid:toggle"]').first();

    const initial = await button.textContent();
    assert(initial.trim() === '答题卡', `初始按钮文案应为「答题卡」，实际「${initial.trim()}」`);
    const initialExpanded = await button.getAttribute('aria-expanded');
    assert(initialExpanded === 'false', `初始 aria-expanded 应为 false，实际 ${JSON.stringify(initialExpanded)}`);
    assert(await page.locator('.qgrid').count() === 0, '答题卡收起时不应存在 .qgrid');

    await button.click();
    await page.waitForFunction(() => document.querySelector('.qgrid'));
    const opened = await button.textContent();
    assert(opened.includes('收起'), `展开后按钮文案应含「收起」，实际「${opened.trim()}」`);
    const openedExpanded = await button.getAttribute('aria-expanded');
    assert(openedExpanded === 'true', `展开后 aria-expanded 应为 true，实际 ${JSON.stringify(openedExpanded)}`);
    assert(await page.locator('.qgrid').count() > 0, '展开后应存在 .qgrid');

    await button.click();
    await page.waitForFunction(() => !document.querySelector('.qgrid'));
    const closed = await button.textContent();
    assert(closed.trim() === '答题卡', `再次收起后按钮文案应回到「答题卡」，实际「${closed.trim()}」`);
    const closedExpanded = await button.getAttribute('aria-expanded');
    assert(closedExpanded === 'false', `再次收起后 aria-expanded 应为 false，实际 ${JSON.stringify(closedExpanded)}`);
    assert(await page.locator('.qgrid').count() === 0, '再次收起后不应残留 .qgrid');
  });

  /* ==========================================================================
   * 4. 模拟考试组卷不重复（连续 5 轮）
   * 防的回归：组卷直接 shuffle 全库 —— 题库里规范化题干重复 133 组、keyConcept 重复 218 组，
   *   一场 20 题撞重复是常态，用户会在一张卷子里看到两道一模一样的题。
   * 每轮先清掉考试存档，确保走的是「全新组卷」路径。
   * ======================================================================== */
  await scenario('4 模拟考试组卷同题干与同知识点均不重复（5 轮）', async () => {
    // 分步执行：任何一步超时都要带上「第几轮 + 当前路由/hash/有无弹窗」，
    // 否则只看到一句 waitForFunction 超时，定位不到是哪一步（本次调试的真实代价）。
    const step = async (round, label, task) => {
      try { await task(); }
      catch (error) {
        const state = await page.evaluate(() => ({
          route: window.__JLX__.state.route,
          hash: window.location.hash,
          exam: !!window.__JLX__.state.exam,
          modal: document.querySelector('#modal-backdrop')?.hidden === false
            ? document.querySelector('#modal-title')?.textContent : '',
        })).catch(() => ({}));
        throw new Error(`第 ${round} 轮「${label}」失败：${String(error.message || error).slice(0, 200)}；`
          + `当时 route=${state.route} hash=${state.hash} exam=${state.exam} 弹窗=${state.modal || '无'}`);
      }
    };
    await fresh();
    for (let round = 1; round <= 5; round++) {
      await step(round, '清考试存档', async () => {
        await page.evaluate((key) => localStorage.removeItem(key), KEY_EXAM);
      });
      await step(round, '重新加载', reload);
      // 上一轮结束在考试路由；「模拟考试」入口卡只在首页，先回首页再点。
      await step(round, '回首页', () => nav('home'));
      await step(round, '点模拟考试入口', () => click('[data-act="exam:new"]'));
      await step(round, '进入考试设置页', () => page.waitForFunction(() => window.__JLX__.state.route === 'exam'));
      await step(round, '点开始考试', async () => {
        await click('[data-act="exam:start"]');
        // 上一轮的考试还在内存里（同一页面连续组卷），生产会先弹「重新开始考试？」确认；
        // 用户就是这么点的，这里照做，取消反而会留在旧考试上。
        await page.waitForTimeout(200);
        const restart = page.locator('#modal-foot button').filter({ hasText: /^重新开始$/ });
        if (await restart.count() && await restart.first().isVisible()) await restart.first().click();
      });
      await step(round, '等待组卷完成', () => page.waitForFunction(() => window.__JLX__.state.exam?.ids?.length > 0));

      const info = await page.evaluate(() => {
        const st = window.__JLX__.state;
        const ids = st.exam.ids.slice();
        return {
          want: st.settings.examCount,
          ids: ids,
          stems: ids.map((id) => st.byId[id].stem),
          concepts: ids.map((id) => st.byId[id].keyConcept),
        };
      });

      console.log(`      第 ${round} 轮：抽到 ${info.ids.length} 题（设置 ${info.want} 题）`);
      // 「题目数与题目数一致」：抽题数量必须等于设置里的题量（题池足够时不该少抽）。
      assert(info.ids.length === info.want,
        `第 ${round} 轮抽题 ${info.ids.length} 题，与设置题量 ${info.want} 不一致`);
      assert(new Set(info.ids).size === info.ids.length, `第 ${round} 轮出现重复题号`);

      const dupStems = duplicateKeys(info.stems.map(stemKey).filter(Boolean));
      assert(dupStems.length === 0,
        `第 ${round} 轮组卷出现重复题干 ${dupStems.length} 处，例如「${dupStems[0]}」`);
      const concepts = info.concepts.map((c) => String(c == null ? '' : c).trim()).filter(Boolean);
      const dupConcepts = duplicateKeys(concepts);
      assert(dupConcepts.length === 0,
        `第 ${round} 轮组卷出现重复知识点 ${dupConcepts.length} 处，例如「${dupConcepts[0]}」`);
    }
  });

  /* ==========================================================================
   * 5. 错题本按章节卡片
   * 防的回归：错题本退化成一条全库平铺列表 —— 跨章节的错题混在一起，
   *   想按章复习只能自己数；或者章节卡片数量与真实章节数不符（漏章/凭空多章）。
   * ======================================================================== */
  await scenario('5 错题本按章节卡片分组且点进去只列该章错题', async () => {
    await fresh();
    const pair = await pickTwoChapters();
    const seed = {};
    // 2 题属第一章、3 题属第二章，跨两章共 5 条错题。
    pair.idsA.slice(0, 2).forEach((id) => { seed[id] = progress({ seen: 1, wrong: 1, wrongFlag: true, lastTs: Date.now() }); });
    pair.idsB.slice(0, 3).forEach((id) => { seed[id] = progress({ seen: 1, wrong: 1, wrongFlag: true, lastTs: Date.now() }); });
    await seedProgress(seed);
    await nav('wrong');

    const cards = page.locator('[data-act="wrong:chapter"]');
    const count = await cards.count();
    assert(count === 2, `两个章节的错题应有 2 张章节卡片，实际 ${count}`);
    const labels = await cards.evaluateAll((els) => els.map((el) => el.getAttribute('data-v')));
    assert(labels.includes(pair.a) && labels.includes(pair.b),
      `章节卡片应覆盖 ${pair.a} / ${pair.b}，实际 ${JSON.stringify(labels)}`);

    // 点进第二章：列表里出现的每个题号都必须属于该章。
    await click(`[data-act="wrong:chapter"][data-v="${pair.b}"]`);
    await page.waitForTimeout(200);
    const listed = await page.evaluate((chapter) => {
      const st = window.__JLX__.state;
      const els = [...document.querySelectorAll('#view [data-act="wrong:remove"], #view [data-act="q:practice"]')];
      const ids = [...new Set(els.map((el) => el.getAttribute('data-id')).filter(Boolean))];
      return { ids: ids, chapters: ids.map((id) => st.byId[id]?.chapter) };
    }, pair.b);
    assert(listed.ids.length > 0, `点开「${pair.b}」章节后列表为空`);
    const foreign = listed.ids.filter((id, i) => listed.chapters[i] !== pair.b);
    assert(foreign.length === 0,
      `「${pair.b}」章节列表里混入了其它章节的题：${JSON.stringify(foreign.slice(0, 3))}`);
  });

  /* ==========================================================================
   * 6. 背题过程可切章节
   * 防的回归：想换一章背只能退出背题、回列表重选（丢当前进度）；
   *   或者点了章节按钮后标题变了、实际背的还是旧章节的题。
   * ======================================================================== */
  await scenario('6 背题过程中切换章节后背的就是该章题目', async () => {
    await fresh({ hash: '#/recite' });
    await page.waitForFunction(() => window.__JLX__.state.route === 'recite');
    await click('[data-act="recite:start"]');
    await page.waitForFunction(() => window.__JLX__.state.sess?.mode === 'recite'
      && window.__JLX__.state.sess.ids.length > 0);

    const switcher = page.locator('[data-act="recite:chapters"]').first();
    assert(await switcher.count() > 0, '背题过程页缺少 [data-act="recite:chapters"] 章节切换入口');
    await switcher.click();
    await page.waitForTimeout(200);

    const target = '第三章军事思想';
    const chapterButton = page.locator('[data-act="recite:chapter"]').filter({ hasText: target }).first();
    assert(await chapterButton.count() > 0,
      `展开章节切换后没有找到「${target}」按钮`);
    await chapterButton.click();
    await page.waitForFunction((c) => {
      const s = window.__JLX__.state.sess;
      return s && s.mode === 'recite' && s.ids.length > 0
        && s.ids.every((id) => window.__JLX__.state.byId[id].chapter === c);
    }, target, { timeout: 8000 });

    const check = await page.evaluate((c) => {
      const st = window.__JLX__.state;
      const ids = st.sess.ids;
      return { n: ids.length, foreign: ids.filter((id) => st.byId[id].chapter !== c).slice(0, 3),
        title: st.sess.title };
    }, target);
    assert(check.foreign.length === 0,
      `切到「${target}」后仍有其它章节的题：${JSON.stringify(check.foreign)}`);
    assert(check.n > 0, `切到「${target}」后背题集合为空`);
  });

  /* ==========================================================================
   * 7. 待复习练习入口
   * 防的回归：待复习数字只是首页上的一行文字，点不进去；或入口文案里的题数
   *   与实际进入的题目集合不一致；或顺序没有按 lastTs 升序（最久没碰的排最后）。
   * ======================================================================== */
  await scenario('7 待复习练习入口题数与题目集合、顺序正确', async () => {
    await fresh();
    const ids = await page.evaluate(() => window.__JLX__.state.questions.slice(0, 5).map((q) => q.id));
    const base = Date.now() - 10 * 86400000;
    const seed = {};
    // 4 条「做过的、box<3」：lastTs 各不相同，用于验证升序；1 条「已掌握」不该进池子。
    ids.slice(0, 4).forEach((id, i) => {
      seed[id] = progress({ seen: 2, correct: 1, wrong: 1, box: 1, lastTs: base + i * 60000 });
    });
    // 打乱写入顺序：如果实现按「遍历顺序」而不是 lastTs 排序，就会露馅。
    const mastered = ids[4];
    const entries = [[ids[2], seed[ids[2]]], [mastered, progress({ seen: 5, correct: 5, box: 3, lastTs: base + 9 * 86400000 })],
      [ids[0], seed[ids[0]]], [ids[3], seed[ids[3]]], [ids[1], seed[ids[1]]]];
    await seedProgress(Object.fromEntries(entries));

    const derived = await page.evaluate(() => window.__JLX__.derive());
    assert(derived.review === 4, `夹具应形成 4 题待复习，实际 derive().review=${derived.review}`);
    assert(derived.mastered === 1, `夹具应形成 1 题已掌握，实际 derive().mastered=${derived.mastered}`);

    await nav('practice');
    const entry = page.locator('[data-act="review:start"]').first();
    assert(await entry.count() > 0, '练习页缺少 [data-act="review:start"] 待复习入口');
    const text = (await entry.textContent()).trim();
    assert(text.includes('4'), `待复习入口文案应含题数 4，实际「${text}」`);

    await entry.click();
    await page.waitForFunction(() => window.__JLX__.state.route === 'practice'
      && window.__JLX__.state.sess?.ids?.length > 0);
    const sess = await page.evaluate(() => window.__JLX__.state.sess.ids.slice());
    const expected = ids.slice(0, 4);   // lastTs 升序 = 夹具里 ids[0..3] 的写入顺序
    assert(sess.length === 4, `待复习练习应恰好包含 4 题，实际 ${sess.length} 题`);
    assert(JSON.stringify(sess) === JSON.stringify(expected),
      `待复习题目集合或顺序不符，期望 ${JSON.stringify(expected)}，实际 ${JSON.stringify(sess)}`);
  });
} finally {
  if (context) await context.close();
  await browser.close();
}

const failures = results.filter((r) => !r.ok);
console.log(JSON.stringify({ suite: 'interaction_fix_20261016', checks: results.length, pass, fail,
  failures, pageErrors: [...new Set(errors)] }, null, 2));
process.exit(fail || errors.length ? 1 : 0);
