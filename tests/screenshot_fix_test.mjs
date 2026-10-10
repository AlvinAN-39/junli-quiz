/**
 * tests/screenshot_fix_test.mjs — 截图 F5–F19 的真实界面回归（长期回归套件，35 项）
 * =====================================================================
 *
 * **这是长期保留的回归套件，不是一次性探针**：删掉它等于删掉 F11/F16/F17/F19
 * 四类场景唯一的代码化验证。场景清单见 docs/截图回归场景清单-35项.md。
 *
 * 覆盖（首跑 29/35 时暴露的是仪器自身缺陷，已修）：
 *   · F11 多选少选时，错因不得把已选的正确选项列为错误；
 *   · F16 未提交草稿（多选/填空/简答）刷新后可恢复，含「查看参考答案」状态；
 *   · F17 损坏的考试存档不提供无效恢复入口，应回落到可用设置；
 *   · F19 浅色/深色/跟随系统三种下，正误标记对比度 ≥ 4.5:1；
 *   另含 F5–F15、F18 等同批次场景，合计 35 项。
 *
 * 环境自适应（CI 无 Playwright 也能跑）：
 *   · Playwright 探测顺序：`JLX_PLAYWRIGHT` → 项目 `node_modules/playwright`
 *     → 同级 `../qa-env/node_modules/playwright`；全部没有则打印 SKIP 并退出码 0；
 *   · 产物 `dist/军理刷题.html` 不存在（CI 的 tests 作业不构建）同样 SKIP 并退出码 0。
 *
 * 夹具注入注意：**不要**「先进生产入口 → 改 localStorage → hash 跳转」，应用离开路由时
 * 会把内存会话写回存档、覆盖夹具。本文件的做法是内存会话与存档同时注入。
 *
 * 用法：node tests/screenshot_fix_test.mjs
 * 输出：每项一行 [PASS]/[FAIL]/[SKIP]，末尾一行 JSON 摘要。
 * 退出码：全部通过 0；存在失败非 0（SKIP 不算失败）。
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const DIST = path.join(ROOT, 'dist', '军理刷题.html');
const URL = pathToFileURL(DIST).href;

/**
 * 探测可用的 Playwright。入库版本不能写本机绝对路径，因此按候选顺序尝试；
 * 全部失败返回 null，由调用处打印 SKIP（CI 属正常情况，不算失败）。
 */
async function loadChromium() {
  const candidates = [
    process.env.JLX_PLAYWRIGHT,
    path.join(ROOT, 'node_modules', 'playwright', 'index.mjs'),
    path.join(ROOT, '..', 'qa-env', 'node_modules', 'playwright', 'index.mjs'),
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      const mod = await import(pathToFileURL(candidate).href);
      if (mod.chromium) return mod.chromium;
    } catch { /* 该候选不可用，继续尝试下一个 */ }
  }
  return null;
}

const KEY_PRACTICE = 'jlx.session.v1';
const KEY_EXAM = 'jlx.exam-session.v1';
const KEY_PROGRESS = 'jlx.progress.v1';
const KEY_SETTINGS = 'jlx.settings.v1';
const artifacts = [];
const results = [];
const errors = [];
let pass = 0;
let fail = 0;

/** 环境不满足（无 Playwright 或无产物）时优雅退出：打印 SKIP 原因，退出码 0。 */
function skipAll(reason) {
  console.log(`[SKIP] 截图 F5–F19 界面回归（35 项） — ${reason}`);
  console.log(JSON.stringify({ suite: 'screenshot_fix', checks: 0, pass: 0, fail: 0,
    skip: 1, reason, skipped: true }, null, 2));
  process.exit(0);
}

const chromium = await loadChromium();
if (!chromium) {
  skipAll('未找到 Playwright（可设置 JLX_PLAYWRIGHT，或在同级 qa-env 安装 playwright）');
}
if (!fs.existsSync(DIST)) {
  skipAll(`未找到产物 ${path.relative(ROOT, DIST)}（先运行 python tools/bundle.py）`);
}

const browser = await chromium.launch();
let context;
let page;
let fixture;

function assert(value, message) {
  if (!value) throw new Error(message);
}
function equal(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

/** 每项失败单独记录，后续场景仍继续运行；逐行输出结果，末尾给 JSON 摘要。 */
async function scenario(name, task) {
  try {
    await task();
    results.push({ name, ok: true });
    pass++;
    console.log(`[PASS] ${name}`);
  } catch (error) {
    const detail = String(error.message || error).slice(0, 500);
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

async function ready() {
  await page.waitForFunction(() => window.__JLX__?.state.questions.length > 0
    && document.querySelector('#view')?.textContent?.trim(), null, { timeout: 20000 });
  // 公告延迟 260ms 出现，必须等其窗口结束后再操作。
  await page.waitForTimeout(450);
  const notice = page.locator('#modal-foot button').filter({ hasText: /^知道了$/ });
  if (await notice.first().isVisible()) await notice.first().click();
}

async function fresh(viewport = { width: 1280, height: 800 }) {
  if (context) await context.close();
  context = await browser.newContext({ viewport, colorScheme: 'light' });
  page = await context.newPage();
  watch(page);
  await page.goto(`${URL}#/home`, { waitUntil: 'load' });
  await ready();
  await page.evaluate((key) => {
    const s = window.__JLX__.state.settings;
    localStorage.setItem(key, JSON.stringify({ ...s, autoNext: false,
      sound: false, haptic: false, shuffleOptions: true, theme: 'light' }));
  }, KEY_SETTINGS);
  await reload();
  fixture = await page.evaluate(() => {
    const qs = window.__JLX__.state.questions;
    const take = (q) => ({ id: q.id, type: q.type, stem: q.stem,
      qa: q.qa, options: q.options });
    const singles = qs.filter((q) => q.type === 'single');
    const multi = qs.find((q) => q.id === 'q-0085') || qs.find((q) => q.type === 'multi'
      && q.qa.some((letter) => q.distractorWhy?.[letter]));
    return {
      single: take(singles[0]), other: take(singles[1]), multi: take(multi),
      fill: take(qs.find((q) => q.type === 'fill')),
      short: take(qs.find((q) => q.type === 'short')),
      judgeFalse: take(qs.find((q) => q.type === 'judge' && q.qa === false))
    };
  });
  assert(fixture.multi?.id && fixture.judgeFalse?.id, '真实题库缺少测试所需题型');
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

async function nav(route) {
  await click(`[data-nav="${route}"]`);
  await page.waitForFunction((r) => window.__JLX__.state.route === r, route);
}

async function modal(label) {
  await page.locator('#modal-foot button').filter({ hasText: new RegExp(`^${label}$`) }).click();
}

async function stored(key) {
  return page.evaluate((k) => {
    const raw = localStorage.getItem(k);
    return raw ? JSON.parse(raw) : null;
  }, key);
}

async function seedProgress(entries) {
  await page.evaluate(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)),
    { key: KEY_PROGRESS, value: entries });
  await reload();
}

function progress(overrides = {}) {
  return { seen: 0, correct: 0, wrong: 0, lastTs: 0, box: 0,
    fav: false, wrongFlag: false, ...overrides };
}

/**
 * 注入夹具题目集合，保留生产创建的存档格式。
 * 注意：若只改 localStorage 再调用 page.goto 切 hash，应用离开练习路由时会把内存会话
 * 写回存档，覆盖本次注入，夹具因此从未真正生效（F11/F16 曾因此误报失败）。
 * 这里同时改内存会话，并仍走生产入口「继续上次练习」恢复。
 */
async function practice(ids, index = 0, extra = {}) {
  await click('[data-act="home:startall"]');
  await page.waitForFunction(() => window.__JLX__.state.sess?.ids?.length > 0);
  await page.evaluate(({ key, ids, index, extra }) => {
    const patch = { ids, i: index, mode: 'practice', order: 'seq', res: {},
      draft: {}, perm: {}, wrongMode: false, revealedRef: {}, ...extra };
    const s = window.__JLX__.state.sess;
    if (!s) throw new Error('生产练习入口未创建会话');
    Object.assign(s, patch);
    const d = JSON.parse(localStorage.getItem(key));
    if (!d) throw new Error('生产练习入口未创建存档');
    Object.assign(d, patch);
    localStorage.setItem(key, JSON.stringify(d));
  }, { key: KEY_PRACTICE, ids, index, extra });
  await page.goto(`${URL}#/home`, { waitUntil: 'load' });
  await ready();
  await click('[data-act="home:continue"]');
  await card('practice');
}

async function resumePractice() {
  await reload();
  await nav('home');
  await click('[data-act="home:continue"]');
  await card('practice');
}

/** 开始考试后限定题目，随后通过生产答题卡按钮刷新真实界面。 */
async function exam(ids) {
  await click('[data-act="exam:new"]');
  const shortSwitch = page.locator('[data-act="exam:short"]');
  if (await shortSwitch.getAttribute('aria-checked') !== 'true') await shortSwitch.click();
  await click('[data-act="exam:start"]');
  await page.evaluate((ids) => {
    const e = window.__JLX__.state.exam;
    Object.assign(e, { ids, i: 0, draft: {}, perm: {}, answered: {}, self: {},
      res: null, paused: false, gridOpen: true, gridPage: 1, withShort: true });
  }, ids);
  await click('[data-act="grid:toggle"]');
  await click('[data-act="grid:toggle"]');
  await card('exam');
}

async function jump(index) {
  if (!await page.locator(`[data-act="nav:jump"][data-i="${index}"]`).isVisible()) {
    await click('[data-act="grid:toggle"]');
  }
  await click(`[data-act="nav:jump"][data-i="${index}"]`);
  await card();
}

async function card(route) {
  await page.waitForFunction((r) => {
    const st = window.__JLX__.state;
    const s = st.route === 'exam' ? st.exam : st.sess;
    return (!r || st.route === r) && s?.ids?.length
      && document.querySelector('#view .q-stem')?.textContent?.trim() === st.byId[s.ids[s.i]]?.stem?.trim();
  }, route || null);
}

async function snapshot() {
  return page.evaluate(() => {
    const st = window.__JLX__.state;
    const s = st.route === 'exam' ? st.exam : st.sess;
    return {
      route: st.route, ids: s?.ids?.slice() || [], i: s?.i, phase: s?.phase,
      paused: !!s?.paused, draft: structuredClone(s?.draft || {}),
      perm: structuredClone(s?.perm || {}), res: structuredClone(s?.res || {}),
      timer: st.examTimer, remaining: s?.remainingMs ?? Math.max(0, (s?.endTs || 0) - Date.now()),
      stem: document.querySelector('#view .q-stem')?.textContent?.trim() || '',
      options: [...document.querySelectorAll('#view .opt')].map((el) => ({
        key: el.getAttribute('data-k'), text: el.textContent.trim(), picked: el.classList.contains('sel')
      }))
    };
  });
}

async function select(letter) {
  await click(`[data-act="ans:pick"][data-k="${letter}"]`);
}

async function finishExam() {
  await click('[data-act="exam:submit"]');
  await modal('交卷');
  const phase = await page.evaluate(() => window.__JLX__.state.exam?.phase);
  if (phase === 'selfcheck') {
    // 未填文字的主观题按不会处理；每次点击可能重绘，重新定位下一题。
    const ids = await page.locator('[data-act="ans:self"][data-v="0"]').evaluateAll((els) =>
      els.map((el) => el.getAttribute('data-id')));
    for (const id of ids) await click(`[data-act="ans:self"][data-v="0"][data-id="${id}"]`);
    await click('[data-act="exam:scoredone"]');
  }
  await page.waitForFunction(() => window.__JLX__.state.exam?.phase === 'report');
}

async function pauseExam(route = 'home') {
  await click(`[data-nav="${route}"]`);
  await page.waitForFunction(() => document.querySelector('#modal-title')?.textContent?.trim() === '暂停考试并离开？');
  await modal('暂停并离开');
  await page.waitForFunction((r) => window.__JLX__.state.route === r, route);
}

async function resumeExam() {
  if (await page.evaluate(() => window.__JLX__.state.route) !== 'home') await nav('home');
  await click('[data-act="exam:new"]');
  await click('[data-act="exam:resume"]');
  await card('exam');
}

async function observeSearch() {
  await page.evaluate(() => {
    window.__qaInput = document.querySelector('[data-act="wrong:search"]');
    window.__qaBatches = 0;
    window.__qaObserver = new MutationObserver((changes) => {
      if (changes.some((r) => r.type === 'childList')) window.__qaBatches++;
    });
    window.__qaObserver.observe(document.querySelector('#view'), { childList: true, subtree: true });
  });
}

async function searchWrongFixture() {
  await fresh();
  await seedProgress({
    [fixture.single.id]: progress({ wrongFlag: true, seen: 1, wrong: 1 }),
    [fixture.other.id]: progress({ wrongFlag: true, seen: 1, wrong: 1 }),
    [fixture.multi.id]: progress({ wrongFlag: true, seen: 1, wrong: 1 })
  });
  await nav('wrong');
}

async function screenshot(name) {
  const path = `${ROOT}/qa/${name}`;
  fs.mkdirSync(`${ROOT}/qa`, { recursive: true });
  await page.screenshot({ path, fullPage: true });
  artifacts.push(path);
}

try {
  await scenario('F5 错题重做存档保留 wrongMode', async () => {
    await fresh();
    await seedProgress({ [fixture.single.id]: progress({ seen: 1, wrong: 1, wrongFlag: true }) });
    await nav('wrong');
    await click('[data-act="wrong:redo"]');
    await page.waitForTimeout(100);
    assert((await stored(KEY_PRACTICE))?.wrongMode === true, '错题重做初始存档未保留标记');
    await resumePractice();
    assert(await page.evaluate(() => window.__JLX__.state.sess.wrongMode === true), '恢复后 wrongMode 丢失');
  });

  await scenario('F5 恢复重做答对后移出错题本', async () => {
    await fresh();
    await seedProgress({ [fixture.single.id]: progress({ seen: 1, wrong: 1, wrongFlag: true }) });
    await nav('wrong');
    await click('[data-act="wrong:redo"]');
    await resumePractice();
    await select(fixture.single.qa);
    assert((await stored(KEY_PROGRESS))[fixture.single.id].wrongFlag === false, '答对未清除错题标记');
    await nav('wrong');
    assert((await page.locator('#view').textContent()).includes('错题本是空的'), '界面错题未移除');
    assert(await page.locator('#badge-wrong').textContent() === '0', '徽章未清零');
  });

  await scenario('F6 未答题不增加已做、累计作答或近七天量', async () => {
    await fresh();
    await exam([fixture.single.id, fixture.multi.id, fixture.fill.id, fixture.short.id, fixture.judgeFalse.id]);
    await select(fixture.single.qa);
    await finishExam();
    const st = await page.evaluate(() => {
      const d = window.__JLX__.derive();
      return { done: d.done, attempts: d.attempts, daily: d.days.reduce((n, x) => n + x.n, 0),
        score: window.__JLX__.state.exam.score };
    });
    assert(st.done === 1 && st.attempts === 1 && st.daily === 1, `未答题污染学习统计：${JSON.stringify(st)}`);
    assert(st.score === 20 && (await page.locator('.score-num').textContent()).trim() === '20', '未答题未按整场考试计错');
  });

  await scenario('F6 未答且答案为错误的判断题不能判对', async () => {
    await fresh();
    await exam([fixture.judgeFalse.id]);
    await finishExam();
    const st = await page.evaluate(() => ({ e: window.__JLX__.state.exam, d: window.__JLX__.derive() }));
    assert(st.e.score === 0 && st.e.res[fixture.judgeFalse.id].ok === false, '未答的 false 判断题被判对');
    assert(st.d.attempts === 0 && (await page.locator('.score-num').textContent()).trim() === '0', '未答题写入记录或成绩界面异常');
  });

  await scenario('F7 答题卡第一、二页题号区间及首格正确', async () => {
    await fresh();
    await click('[data-act="home:startall"]');
    await click('[data-act="grid:toggle"]');
    let text = await page.locator('#view .card-title').filter({ hasText: '答题卡' }).textContent();
    assert(/1-100\s*\//.test(text) && !/01-100/.test(text), `第一页标题错误：${text}`);
    await click('[data-act="grid:page"][data-v="2"]');
    text = await page.locator('#view .card-title').filter({ hasText: '答题卡' }).textContent();
    assert(/101-200\s*\//.test(text) && (await page.locator('.qgrid .qcell').first().textContent()) === '101', `第二页标题或首格错误：${text}`);
  });

  await scenario('F8 考试提示自动保存而非点选判分', async () => {
    await fresh();
    await exam([fixture.single.id]);
    const text = await page.locator('#view .q-card').textContent();
    assert(/自动保存/.test(text) && !/点选即判分/.test(text), `考试提示不正确：${text.slice(-200)}`);
    await select(fixture.single.qa);
    assert(await page.locator('.verdict').count() === 0, '考试进行中提前显示判分');
  });

  await scenario('F8 考试多选与填空自动保存且没有无效提交按钮', async () => {
    await fresh();
    await exam([fixture.multi.id]);
    assert(await page.locator('[data-act="ans:submit"]').count() === 0, '考试仍有练习提交按钮');
    await select(fixture.multi.qa[0]);
    await page.waitForTimeout(100);
    assert(equal((await stored(KEY_EXAM))?.draft?.[fixture.multi.id], [fixture.multi.qa[0]]), '考试多选未存草稿');
    assert(await page.locator('.opt.sel').count() === 1, '考试多选界面没有选中态');
    await fresh();
    await exam([fixture.fill.id]);
    assert(await page.locator('[data-act="ans:submit"]').count() === 0, '考试填空仍有练习提交按钮');
    await page.locator('[data-act="ans:fill"]').first().fill('未提交的填空');
    await page.waitForTimeout(100);
    assert((await stored(KEY_EXAM))?.draft?.[fixture.fill.id]?.[0] === '未提交的填空', '填空未自动存盘');
  });

  await scenario('F9 未作答收藏在首页、列表、徽章一致', async () => {
    await fresh();
    await click('[data-act="recite:start"]');
    await click('.q-head [data-act="fav"]');
    const st = await page.evaluate(() => ({ d: window.__JLX__.derive(), id: window.__JLX__.state.sess.ids[0] }));
    assert(st.d.fav === 1 && st.d.done === 0, '未答收藏被统计忽略或误增已做');
    await nav('home');
    assert(await page.locator('#badge-fav').textContent() === '1', '收藏徽章不一致');
    await nav('fav');
    assert(await page.locator('[data-act="fav"]').count() === 1 && (await page.locator('.card-sub').first().textContent()).trim() === '1 题', '收藏夹数量不一致');
  });

  await scenario('F9 导入未作答错题标记仍正确计数', async () => {
    await fresh();
    await seedProgress({ [fixture.single.id]: progress({ wrongFlag: true }) });
    const d = await page.evaluate(() => window.__JLX__.derive());
    assert(d.wrong === 1 && d.done === 0, '未答错题标记被忽略或误增已做');
    await nav('wrong');
    assert(await page.locator('[data-act="wrong:remove"]').count() === 1 && await page.locator('#badge-wrong').textContent() === '1', '错题列表/徽章不一致');
  });

  await scenario('F10 搜索280ms防抖只更新一次且保留输入节点', async () => {
    await searchWrongFixture();
    await observeSearch();
    await page.locator('[data-act="wrong:search"]').fill(fixture.single.stem);
    await page.waitForTimeout(110);
    assert(await page.evaluate(() => window.__qaBatches === 0), '防抖窗口内已重建结果');
    await page.waitForTimeout(260);
    const observation = await page.evaluate(() => ({ batches: window.__qaBatches,
      same: window.__qaInput === document.querySelector('[data-act="wrong:search"]'),
      focused: document.activeElement === window.__qaInput }));
    assert(observation.batches === 1 && observation.same && observation.focused,
      `搜索更新或焦点异常：${JSON.stringify(observation)}`);
    assert(await page.locator('[data-act="wrong:remove"]').count() === 1, '搜索未筛到唯一真实题目');
  });

  await scenario('F10 中文组合输入结束前不重绘', async () => {
    await searchWrongFixture();
    await observeSearch();
    const input = page.locator('[data-act="wrong:search"]');
    await input.dispatchEvent('compositionstart', { data: '' });
    await input.fill('国防');
    await page.waitForTimeout(340);
    assert(await page.evaluate(() => window.__qaBatches === 0), '中文组合输入期间重绘结果');
    await input.dispatchEvent('compositionend', { data: '国防' });
    await page.waitForTimeout(350);
    assert(await page.evaluate(() => window.__qaInput === document.querySelector('[data-act="wrong:search"]')
      && document.activeElement === window.__qaInput), '组合输入结束后节点或焦点丢失');
  });

  await scenario('F10 离开错题页后旧回调不重绘或抢焦点', async () => {
    await searchWrongFixture();
    await page.locator('[data-act="wrong:search"]').fill('国防');
    await nav('home');
    const before = await page.locator('#view').innerHTML();
    await page.waitForTimeout(400);
    assert(await page.locator('#view').innerHTML() === before, '旧搜索回调重绘首页');
    assert(await page.evaluate(() => window.__JLX__.state.route === 'home'
      && document.activeElement?.getAttribute('data-act') !== 'wrong:search'), '旧搜索回调抢焦点');
  });

  await scenario('F11 多选少选时不把正确选项列为错因', async () => {
    await fresh();
    await practice([fixture.multi.id]);
    const covered = await page.evaluate((id) => {
      const q = window.__JLX__.state.byId[id];
      // 当前题库已清理正确项错因；模拟旧数据，确保渲染防线仍能阻止回归。
      const letter = q.qa[0];
      q.distractorWhy = { ...q.distractorWhy, [letter]: '旧数据误把正确项写成错误项' };
      return letter;
    }, fixture.multi.id);
    assert(covered && fixture.multi.qa.length > 1, '夹具不能触发少选正确项错因');
    await select(covered);
    await click('[data-act="ans:submit"]');
    assert(await page.locator('.verdict.bad').count() === 1, '少选未判错');
    assert(await page.locator('.kw-why').count() === 0, '正确选项仍被列为选错原因');
  });

  await scenario('F12 收藏列表取消最后一题立即显示空态', async () => {
    await fresh();
    await seedProgress({ [fixture.single.id]: progress({ fav: true }) });
    await nav('fav');
    await click(`[data-act="fav"][data-id="${fixture.single.id}"]`);
    assert((await page.locator('#view').textContent()).includes('还没有收藏题目'), '取消收藏后行未移除或空态未显示');
    assert(await page.locator('#badge-fav').textContent() === '0'
      && (await stored(KEY_PROGRESS))[fixture.single.id].fav === false, '收藏数据与徽章未清零');
  });

  await scenario('F13 背题后练习设置与顶栏标题一致', async () => {
    await fresh();
    await click('[data-act="recite:start"]');
    await nav('practice');
    const title = (await page.locator('#page-title').textContent()).trim();
    assert((await page.locator('#view').textContent()).includes('练习设置')
      && title.includes('练习') && !title.includes('背题'), `标题与内容冲突：${title}`);
    assert(await page.locator('#progress-text').isVisible() === false, '练习设置仍显示背题进度');
  });

  await scenario('F14 首页与统计均使用按题去重正确率', async () => {
    await fresh();
    await seedProgress({ [fixture.single.id]: progress({ seen: 2, correct: 1, wrong: 1, lastTs: Date.now() }) });
    const d = await page.evaluate(() => window.__JLX__.derive());
    assert(d.rate === 50 && d.uniqueRate === 100, '统计夹具未形成两个不同口径');
    const homeStat = page.locator('#view .stat').filter({ hasText: '正确率' }).first();
    assert((await homeStat.locator('b').textContent()).trim() === '100%', '首页仍用按次数的50%');
    await nav('stats');
    const statsStat = page.locator('#view .stat').filter({ hasText: '正确率' }).first();
    assert((await statsStat.locator('b').textContent()).trim() === '100%', '统计页未用按题去重正确率');
  });

  for (const [size, factor] of [['s', 0.9], ['m', 1], ['l', 1.13], ['xl', 1.28]]) {
    await scenario(`F15 窄屏字号${size}仅缩放一次且无溢出`, async () => {
      await fresh({ width: 390, height: 844 });
      await nav('settings');
      await click(`[data-act="set:font"][data-v="${size}"]`);
      await nav('home');
      await practice([fixture.single.id]);
      const css = await page.evaluate(() => ({
        root: parseFloat(getComputedStyle(document.documentElement).fontSize),
        body: parseFloat(getComputedStyle(document.body).fontSize),
        stem: parseFloat(getComputedStyle(document.querySelector('.q-stem')).fontSize),
        opt: parseFloat(getComputedStyle(document.querySelector('.opt')).fontSize),
        width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth
      }));
      assert(Math.abs(css.root - 16 * factor) < 0.05 && Math.abs(css.stem - css.root * 1.06) < 0.05
        && Math.abs(css.opt - css.root * 0.98) < 0.05 && css.stem > css.body,
      `存在重复缩放：${JSON.stringify(css)}`);
      assert(css.scroll <= css.width + 1, `字号${size}横向溢出：${css.scroll}/${css.width}`);
      if (size === 'xl') await screenshot('截图修复-字号特大-390px.png');
    });
  }

  await scenario('F16 练习乱序排列刷新恢复后屏幕完全一致', async () => {
    await fresh();
    await practice([fixture.single.id]);
    const before = await snapshot();
    await resumePractice();
    const after = await snapshot();
    assert(equal(before.perm, after.perm) && equal(before.options, after.options)
      && before.stem === after.stem, '恢复后选项排列或题干变化');
    assert(equal((await stored(KEY_PRACTICE)).perm, after.perm), '屏幕排列没有落盘');
  });

  await scenario('F16 未提交多选草稿刷新后保留', async () => {
    await fresh();
    await practice([fixture.multi.id]);
    await select(fixture.multi.qa[0]);
    await resumePractice();
    const st = await snapshot();
    assert(equal(st.draft[fixture.multi.id], [fixture.multi.qa[0]])
      && st.options.filter((x) => x.picked).length === 1, '未提交多选草稿丢失或界面未选中');
    assert(await page.locator('[data-act="ans:submit"]').isVisible(), '恢复后的未提交多选被错误锁定');
  });

  await scenario('F16 填空草稿立即刷新后保留', async () => {
    await fresh();
    await practice([fixture.fill.id]);
    await page.locator('[data-act="ans:fill"]').first().fill('刷新前尚未提交');
    await resumePractice();
    assert(await page.locator('[data-act="ans:fill"]').first().inputValue() === '刷新前尚未提交'
      && (await stored(KEY_PRACTICE)).draft[fixture.fill.id][0] === '刷新前尚未提交', '填空末次输入未同步保存');
  });

  await scenario('F16 简答草稿及查看参考答案状态均恢复', async () => {
    await fresh();
    await practice([fixture.short.id]);
    await page.locator('[data-act="ans:short"]').fill('我的未提交简答草稿');
    await click('[data-act="ans:reveal"]');
    await resumePractice();
    const st = await stored(KEY_PRACTICE);
    assert(st.draft[fixture.short.id] === '我的未提交简答草稿'
      && st.revealedRef?.[fixture.short.id] === true, '简答草稿或参考答案状态未存盘');
    assert(await page.locator('.answer-box').isVisible() && await page.locator('[data-act="ans:self"]').count() === 2, '恢复后参考答案或自评按钮缺失');
  });

  await scenario('F17 离开考试取消后保持题目、草稿和计时', async () => {
    await fresh();
    await exam([fixture.single.id, fixture.multi.id]);
    await select(fixture.single.qa);
    const before = await snapshot();
    await click('[data-nav="home"]');
    assert((await page.locator('#modal-title').textContent()).trim() === '暂停考试并离开？', '离开未出现指定确认框');
    await modal('取消');
    const after = await snapshot();
    assert(after.route === 'exam' && !after.paused && after.timer
      && equal(after.ids, before.ids) && equal(after.draft, before.draft), '取消退出后考试状态被改变');
    await card('exam');
  });

  await scenario('F17 确认离开保存并停表且不会后台交卷', async () => {
    await fresh();
    await exam([fixture.single.id]);
    await pauseExam();
    const before = await stored(KEY_EXAM);
    const count = await page.evaluate(() => window.__JLX__.state.exams.length);
    await page.waitForTimeout(750);
    const after = await stored(KEY_EXAM);
    assert(before?.paused === true && after?.paused === true
      && before.remainingMs === after.remainingMs, '暂停存档或剩余时间不稳定');
    assert(await page.evaluate((n) => window.__JLX__.state.examTimer === 0
      && window.__JLX__.state.exams.length === n && window.__JLX__.derive().attempts === 0, count), '离开后仍计时、后台评分或写学习记录');
  });

  await scenario('F17 暂停考试可由设置入口继续相同状态', async () => {
    await fresh();
    await exam([fixture.single.id, fixture.multi.id]);
    await jump(1);
    await select(fixture.multi.qa[0]);
    const before = await snapshot();
    await pauseExam();
    const saved = await stored(KEY_EXAM);
    await resumeExam();
    const after = await snapshot();
    assert(equal(before.ids, after.ids) && before.i === after.i && equal(before.draft, after.draft)
      && equal(before.perm, after.perm) && before.stem === after.stem, '继续考试的集合/位置/草稿/排列丢失');
    assert(!after.paused && after.timer && Math.abs(after.remaining - saved.remainingMs) < 1500, '恢复后计时不是剩余时间');
    assert(after.options.filter((x) => x.picked).length === 1, '恢复后多选未在界面选中');
  });

  await scenario('F17 刷新考试后暂停并可显式继续', async () => {
    await fresh();
    await exam([fixture.fill.id]);
    await page.locator('[data-act="ans:fill"]').first().fill('考试刷新草稿');
    const before = await snapshot();
    await reload();
    assert((await stored(KEY_EXAM))?.paused === true, '考试刷新没有保存暂停状态');
    assert(await page.locator('[data-act="exam:resume"]').isVisible(), '刷新后缺少继续考试入口');
    await click('[data-act="exam:resume"]');
    await card('exam');
    assert(equal(before.ids, (await snapshot()).ids)
      && await page.locator('[data-act="ans:fill"]').first().inputValue() === '考试刷新草稿', '刷新后继续考试丢失草稿/集合');
  });

  await scenario('F17 关闭重开页面后考试可继续', async () => {
    await fresh();
    await exam([fixture.multi.id]);
    await select(fixture.multi.qa[0]);
    const before = await snapshot();
    await page.close();
    page = await context.newPage();
    watch(page);
    await page.goto(`${URL}#/exam`, { waitUntil: 'load' });
    await ready();
    assert(await page.locator('[data-act="exam:resume"]').isVisible(), '关页后缺少恢复入口');
    await click('[data-act="exam:resume"]');
    await card('exam');
    const after = await snapshot();
    assert(equal(before.ids, after.ids) && equal(before.draft, after.draft)
      && equal(before.perm, after.perm) && after.options.some((x) => x.picked), '关页恢复状态不一致');
  });

  await scenario('F17 浏览器返回也必须经过退出确认', async () => {
    await fresh();
    await exam([fixture.single.id]);
    await page.goBack();
    await page.waitForFunction(() => document.querySelector('#modal-title')?.textContent?.trim() === '暂停考试并离开？');
    await modal('取消');
    await card('exam');
    assert(await page.evaluate(() => window.__JLX__.state.route === 'exam'
      && window.__JLX__.state.exam?.paused !== true), '浏览器返回取消后考试未保留');
  });

  await scenario('F17 可明确放弃旧考试再开始新考试', async () => {
    await fresh();
    await exam([fixture.single.id]);
    await select(fixture.single.qa);
    await pauseExam();
    await click('[data-act="exam:new"]');
    assert(await page.locator('[data-act="exam:resume"]').isVisible(), '进入设置时旧存档被静默覆盖');
    await click('[data-act="exam:discard"]');
    if (await page.locator('#modal-backdrop').isVisible()) {
      await page.locator('#modal-foot button').filter({ hasText: /放弃/ }).click();
    }
    assert(await page.locator('[data-act="exam:resume"]').count() === 0, '放弃后旧考试仍显示恢复入口');
    assert(await stored(KEY_EXAM) === null, '放弃旧考试未清除考试存档');
    await click('[data-act="exam:start"]');
    await card('exam');
    assert(await page.evaluate(() => Object.keys(window.__JLX__.state.exam.draft).length === 0
      && window.__JLX__.state.exams.length === 0), '新考试继承旧草稿或放弃被当作交卷');
  });

  await scenario('F17 损坏考试题号不提供无效恢复入口', async () => {
    await fresh();
    await exam([fixture.single.id]);
    await pauseExam();
    // 「重新打开页面后读到损坏存档」：必须在文档脚本执行前篡改，
    // 否则 pagehide 保存会用内存中的有效考试覆盖篡改，测不到损坏场景。
    await page.addInitScript((key) => {
      try {
        const raw = localStorage.getItem(key);
        if (!raw) return;
        const d = JSON.parse(raw);
        d.ids = ['题库中不存在的考试题号'];
        localStorage.setItem(key, JSON.stringify(d));
      } catch (e) { /* 首次加载尚无存档时跳过 */ }
    }, KEY_EXAM);
    await page.reload({ waitUntil: 'load' });
    await ready();
    await page.goto(`${URL}#/exam`, { waitUntil: 'load' });
    await ready();
    assert(await page.locator('[data-act="exam:resume"]').count() === 0
      && await page.locator('[data-act="exam:start"]').isVisible(), '损坏存档未回落到可用考试设置');
  });

  await scenario('F18 考试中隐藏参考答案按钮而交卷后自评正确计分', async () => {
    await fresh();
    await exam([fixture.short.id]);
    assert(await page.locator('[data-act="ans:reveal"]').count() === 0, '考试中仍有死参考答案按钮');
    await page.locator('[data-act="ans:short"]').fill('已填写的简答作答');
    await click('[data-act="exam:submit"]');
    await modal('交卷');
    assert(await page.evaluate(() => window.__JLX__.state.exam.phase === 'selfcheck'), '交卷后未进入自评');
    await click(`[data-act="ans:self"][data-v="1"][data-id="${fixture.short.id}"]`);
    await click('[data-act="exam:scoredone"]');
    assert((await page.locator('.score-num').textContent()).trim() === '100'
      && await page.evaluate((id) => window.__JLX__.state.exam.res[id].ok === true
      && window.__JLX__.state.progress[id].correct === 1, fixture.short.id), '自评为会没有同步到判分和学习记录');
  });

  await scenario('F18 自评刷新可恢复且评分不重复写记录', async () => {
    await fresh();
    await exam([fixture.short.id]);
    await page.locator('[data-act="ans:short"]').fill('自评恢复草稿');
    await click('[data-act="exam:submit"]');
    await modal('交卷');
    await click(`[data-act="ans:self"][data-v="1"][data-id="${fixture.short.id}"]`);
    await reload();
    if (await page.locator('[data-act="exam:resume"]').isVisible()) await click('[data-act="exam:resume"]');
    assert(await page.evaluate((id) => window.__JLX__.state.exam.phase === 'selfcheck'
      && window.__JLX__.state.exam.self[id] === true, fixture.short.id), '自评阶段或已选结果没有恢复');
    await page.locator('[data-act="exam:scoredone"]').dblclick();
    await reload();
    assert(await page.evaluate((id) => window.__JLX__.state.exams.length === 1
      && window.__JLX__.state.progress[id].seen === 1, fixture.short.id), '重复点击或刷新重复评分');
    assert(await page.locator('[data-act="exam:resume"]').count() === 0, '已评分考试仍可作为未完成会话恢复');
  });

  await scenario('F19 浅色、深色及系统深色正误标记均达到4.5对比度', async () => {
    await fresh({ width: 390, height: 844 });
    await practice([fixture.single.id, fixture.other.id]);
    await select(fixture.single.qa);
    await click('[data-act="nav:next"]');
    await select('ABCDEFGHIJ'.slice(0, fixture.other.options.length).split('').find((x) => x !== fixture.other.qa));
    await click('[data-act="grid:toggle"]');
    const colors = async () => page.evaluate(() => {
      const lum = (rgb) => {
        const v = rgb.match(/[\d.]+/g).slice(0, 3).map((n) => Number(n) / 255)
          .map((n) => n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4);
        return v[0] * 0.2126 + v[1] * 0.7152 + v[2] * 0.0722;
      };
      return ['.opt.right .opt-key', '.opt.wrong .opt-key', '.qcell.right', '.qcell.wrong'].map((selector) => {
        const el = document.querySelector(selector);
        if (!el) return { selector, ratio: 0, missing: true };
        const style = getComputedStyle(el), a = lum(style.color), b = lum(style.backgroundColor);
        return { selector, ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
          color: style.color, bg: style.backgroundColor, cls: el.className };
      });
    });
    for (const theme of ['light', 'dark', 'auto']) {
      if (theme === 'auto') await page.emulateMedia({ colorScheme: 'dark' });
      for (let i = 0; i < 4 && await page.locator('html').getAttribute('data-theme') !== theme; i++) await click('#btn-theme');
      // .qcell 带 background .15s 过渡：切换主题后必须等过渡结束再读计算样式，
      // 否则会读到切换前的颜色（深色下曾因此把浅色底误算成 3.81 对比度）。
      await page.waitForTimeout(300);
      assert(await page.locator('html').getAttribute('data-theme') === theme, `无法通过界面切换到${theme}`);
      const ratios = await colors();
      assert(ratios.every((x) => x.ratio >= 4.5), `${theme}对比度不足：${JSON.stringify(ratios)}`);
      if (theme === 'dark') await screenshot('截图修复-深色正误标记-390px.png');
    }
  });
} finally {
  if (context) await context.close();
  await browser.close();
}

const failures = results.filter((r) => !r.ok);
console.log(JSON.stringify({ suite: 'screenshot_fix', checks: results.length, pass, fail,
  failures, pageErrors: [...new Set(errors)], artifacts }, null, 2));
process.exit(fail || errors.length ? 1 : 0);
