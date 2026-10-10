/** 全项目边界回归：使用生产界面操作，夹具仅用于构造旧存档及损坏备份。 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let chromium;
for (const candidate of [process.env.JLX_PLAYWRIGHT, path.join(ROOT, 'node_modules/playwright/index.mjs'), path.join(ROOT, '../qa-env/node_modules/playwright/index.mjs')].filter(Boolean)) {
  try { chromium = (await import(pathToFileURL(candidate).href)).chromium; if (chromium) break; } catch { /* 使用下一项本地依赖。 */ }
}
const artifact = path.join(ROOT, 'dist/军理刷题.html');
if (!chromium || !fs.existsSync(artifact)) { console.log('[SKIP] 全项目界面回归需要 Playwright 与打包产物'); process.exit(0); }
const browser = await chromium.launch();
let context, page;
const results = [];
const assert = (ok, message) => { if (!ok) throw Error(message); };
const errors = [];
async function fresh(storage = {}) {
  if (context) await context.close();
  context = await browser.newContext();
  page = await context.newPage();
  page.on('pageerror', e => errors.push(String(e)));
  await page.addInitScript(storage => {
    for (const [key, value] of Object.entries(storage)) localStorage.setItem(key, JSON.stringify(value));
  }, storage);
  await page.goto(pathToFileURL(artifact).href);
  await page.waitForFunction(() => window.__JLX__?.state.questions.length === 1531);
  await page.waitForTimeout(350);
  const notice = page.getByRole('button', { name: '知道了', exact: true });
  if (await notice.isVisible()) await notice.click();
  await page.evaluate(() => { const s = window.__JLX__.state.settings; s.sound = false; s.haptic = false; s.autoNext = false; });
}
async function nav(route) {
  const button = page.locator(`[data-nav="${route}"]:visible`).first();
  if (await button.count()) await button.click();
  else { await page.evaluate(route => { location.hash = '#/' + route; }, route); await page.waitForFunction(route => window.__JLX__.state.route === route, route); }
}
async function importData(data, mode = 'replace') {
  await nav('sync');
  await page.locator('#import-area').fill(JSON.stringify(data));
  await page.locator(`[data-act="sync:${mode}"]`).click();
  const confirm = page.getByRole('button', { name: '确定导入', exact: true });
  if (await confirm.isVisible()) await confirm.click();
}
async function check(name, fn) {
  try { await fn(); results.push({ name, ok: true }); console.log('[PASS] ' + name); }
  catch (e) { results.push({ name, ok: false, error: e.message }); console.log('[FAIL] ' + name + '：' + e.message); }
}
const exam = { ts: 123, total: 1, correct: 1, score: 100, durationMs: 1000, detail: [] };
try {
  await check('所有主页面可打开且无渲染错误', async () => {
    await fresh();
    for (const route of ['home', 'practice', 'exam', 'recite', 'wrong', 'fav', 'search', 'stats', 'sync', 'settings', 'outline']) {
      await nav(route);
      assert(!(await page.locator('#view').textContent()).includes('页面渲染出错'), route + ' 渲染失败');
      assert((await page.locator('#view').textContent()).trim().length > 0, route + ' 无可用内容');
    }
  });
  await check('设置页顶栏显示设置标题', async () => {
    await fresh(); await nav('settings');
    assert((await page.locator('#page-title').textContent()) === '设置', '设置页顶栏仍显示应用名');
  });
  await check('考试草稿计数即时更新并在清空后减少', async () => {
    await fresh(); await nav('exam'); await page.locator('[data-act="exam:start"]').click();
    await page.evaluate(() => {
      const s = window.__JLX__.state, q = s.questions.find(q => q.type === 'fill');
      Object.assign(s.exam, { ids: [q.id], i: 0, draft: {}, gridOpen: false });
    });
    await page.locator('[data-act="grid:toggle"]').click();
    const input = page.locator('[data-act="ans:fill"]').first();
    await input.fill('草稿');
    assert((await page.locator('#view').textContent()).includes('已答 1/1 题'), '输入后已答题数仍为零');
    await input.fill('');
    assert((await page.locator('#view').textContent()).includes('已答 0/1 题'), '清空后已答题数未减少');
    assert(await input.evaluate(el => document.activeElement === el), '更新题数使输入框失焦');
  });
  await check('有效备份往返保留计数、标记、日期与成绩', async () => {
    await fresh();
    const data = { app: '军理刷题', ver: 1, progress: { 'q-0001': { seen: 3, correct: 2, wrong: 1, fav: true, wrongFlag: true, box: 2 } }, exams: [exam], daily: { '2026-10-10': { n: 3, ok: 2 } } };
    await importData(data);
    const exported = await page.evaluate(() => JSON.parse(window.__JLX__.exportText()));
    await importData(exported);
    const saved = await page.evaluate(() => JSON.parse(window.__JLX__.exportText()));
    assert(JSON.stringify(saved.progress) === JSON.stringify(exported.progress), '有效进度被清洗改变');
    assert(JSON.stringify(saved.exams) === JSON.stringify(exported.exams), '有效成绩被清洗改变');
  });
  await check('拒绝其它应用和未来版本的备份', async () => {
    await fresh(); await nav('sync');
    for (const data of [{ app: '其它应用', progress: {} }, { ver: 999, progress: {} }]) {
      await page.locator('#import-area').fill(JSON.stringify(data));
      await page.locator('[data-act="sync:replace"]').click();
      assert(!(await page.getByRole('button', { name: '确定导入', exact: true }).isVisible()), '不兼容备份进入覆盖确认');
    }
  });
  await check('有效旧作答结果恢复后保持判定与草稿', async () => {
    await fresh({ 'jlx.session.v1': { ver: 1, ids: ['q-0047'], order: 'seq', i: 0, res: { 'q-0047': { picked: 'D', ok: true, ts: 123 } }, draft: { 'q-0047': 'D' } } });
    await page.locator('[data-act="home:continue"]').click();
    assert(await page.locator('.verdict.ok').count() === 1, '有效旧结果被丢弃');
    assert(await page.evaluate(() => window.__JLX__.state.sess.draft['q-0047'] === 'D'), '原始答案草稿被修改');
  });
  await check('手机与桌面各主页面没有横向溢出', async () => {
    await fresh();
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 844 });
      for (const route of ['home', 'practice', 'exam', 'recite', 'wrong', 'fav', 'search', 'stats', 'sync', 'settings', 'outline']) {
        await nav(route);
        const w = await page.evaluate(() => ({ actual: document.documentElement.scrollWidth, available: document.documentElement.clientWidth }));
        assert(w.actual <= w.available + 1, route + '/' + width + ' 横向溢出：' + JSON.stringify(w));
      }
    }
  });
  await check('重复合并备份不复制已有考试成绩', async () => {
    await fresh();
    const data = { app: '军理刷题', ver: 1, progress: {}, exams: [exam] };
    await importData(data, 'merge'); await importData(data, 'merge');
    const count = await page.evaluate(() => window.__JLX__.state.exams.length);
    assert(count === 1, '考试成绩重复，记录数=' + count);
  });
  await check('覆盖导入清空内存练习与背题会话', async () => {
    await fresh(); await page.locator('[data-act="home:startall"]').click();
    await importData({ progress: {} });
    assert(await page.evaluate(() => window.__JLX__.state.sess === null), '旧练习会话仍留在内存');
    await nav('practice');
    assert(await page.locator('.q-card').count() === 0, '旧题卡覆盖导入后仍可继续作答');
  });
  await check('进度字段为数组的备份被拒绝且不清空本机数据', async () => {
    await fresh(); await importData({ progress: { 'q-0001': { seen: 1, correct: 1 } } });
    await nav('sync'); await page.locator('#import-area').fill(JSON.stringify({ progress: [] }));
    await page.locator('[data-act="sync:replace"]').click();
    assert(!(await page.getByRole('button', { name: '确定导入', exact: true }).isVisible()), '数组进度被当成有效覆盖备份');
    assert(await page.evaluate(() => window.__JLX__.state.progress['q-0001'].seen === 1), '拒绝前已改变本机数据');
  });
  await check('无效成绩记录不会导致考试设置页报错', async () => {
    await fresh(); await importData({ progress: {}, exams: [null, {}, exam] }); await nav('exam');
    assert(!(await page.locator('#view').textContent()).includes('页面渲染出错'), '导入空成绩使考试页渲染出错');
    assert(await page.evaluate(() => window.__JLX__.state.exams.length === 1), '无效成绩未剔除');
  });
  await check('导入负数与矛盾计数后统计仍合法', async () => {
    await fresh();
    await importData({ progress: { 'q-0001': { seen: -2, correct: -3, wrong: 4, box: 99 } }, daily: { '2026-10-10': { n: 1, ok: 9 } } });
    const p = await page.evaluate(() => { const s = window.__JLX__.state; return { q: s.progress['q-0001'], d: s.progress.__daily['2026-10-10'] }; });
    assert(p.q.seen >= 0 && p.q.correct >= 0 && p.q.wrong >= 0 && p.q.box <= 5 && p.q.seen >= p.q.correct + p.q.wrong, '题目计数不合法：' + JSON.stringify(p.q));
    assert(p.d.ok <= p.d.n, '每日正确次数大于作答次数');
  });
  await check('启动时清洗旧本地进度中的字符串计数', async () => {
    await fresh({ 'jlx.progress.v1': { 'q-0001': { seen: '2', correct: '1', wrong: '1', box: 1 }, __daily: {} } });
    const d = await page.evaluate(() => window.__JLX__.derive());
    assert(d.attempts === 2 && d.correct === 1, '统计被字符串拼接：' + JSON.stringify({ attempts: d.attempts, correct: d.correct }));
  });
  await check('恢复损坏的填空作答记录不使练习页面报错', async () => {
    await fresh({ 'jlx.session.v1': { ver: 1, ids: ['q-0913'], order: 'seq', i: 0, res: { 'q-0913': { picked: '错误文本', ok: false } } } });
    await page.locator('[data-act="home:continue"]').click();
    assert(!(await page.locator('#view').textContent()).includes('页面渲染出错'), '损坏填空结果导致题卡崩溃');
    assert(await page.locator('.q-card').count() === 1, '恢复后没有题卡');
  });
  await check('存储额度不足时当前会话恢复使用最新内存副本', async () => {
    await fresh(); await page.locator('[data-act="home:startall"]').click();
    await page.evaluate(() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        if (key === 'jlx.session.v1') throw new DOMException('测试额度耗尽', 'QuotaExceededError');
        return original.call(this, key, value);
      };
    });
    await page.locator('[data-act="nav:next"]').click();
    await page.locator('[data-act="sess:exit"]').click();
    await page.getByRole('button', { name: '退出', exact: true }).click();
    await nav('practice'); await page.locator('[data-act="prac:continue"]').click();
    assert(await page.evaluate(() => window.__JLX__.state.sess.i === 1), '读到旧磁盘存档，丢失最后一次翻页');
    assert((await page.locator('#view').textContent()).includes('关页前请导出备份'), '存储失败后仍未提醒导出');
  });
  await check('第101题的填空输入实时更新第二页答题卡', async () => {
    await fresh(); await nav('exam'); await page.locator('[data-act="exam:start"]').click();
    const id = await page.evaluate(() => {
      const s = window.__JLX__.state, q = s.questions.find(q => q.type === 'fill');
      const ids = s.questions.filter(x => x.id !== q.id).slice(0, 100).map(q => q.id).concat(q.id);
      Object.assign(s.exam, { ids, i: 100, gridOpen: false, draft: {}, gridPage: 2 });
      return q.id;
    });
    await page.locator('[data-act="grid:toggle"]').click();
    await page.locator('[data-act="ans:fill"]').first().fill('测试草稿');
    assert(await page.locator('.qcell[data-i="100"]').evaluate(el => el.classList.contains('done')), '第101题有草稿但仍显示未答');
    assert(await page.evaluate(id => window.__JLX__.state.exam.draft[id][0] === '测试草稿', id), '实际草稿未写入');
  });
  await check('练习未提交多选草稿不被答题卡标为已答', async () => {
    await fresh(); await page.locator('[data-act="home:startall"]').click();
    await page.evaluate(() => { const s = window.__JLX__.state; s.sess.ids = ['q-0085']; s.sess.i = 0; s.sess.res = {}; s.sess.draft = {}; });
    await page.locator('[data-act="grid:toggle"]').click();
    await page.locator('[data-act="ans:pick"]').first().click();
    assert(!(await page.locator('.qcell[data-i="0"]').evaluate(el => el.classList.contains('done'))), '未提交草稿被标为已答');
  });
  await check('无作答的收藏与错题数量在全部入口一致', async () => {
    await fresh(); await importData({ progress: { 'q-0001': { fav: true, wrongFlag: true } } });
    const d = await page.evaluate(() => window.__JLX__.derive());
    assert(d.fav === 1 && d.wrong === 1 && d.done === 0, '标记统计不一致');
    await nav('fav'); assert(await page.locator('.list-item').count() === 1, '收藏列表丢题');
    await nav('wrong'); assert(await page.locator('[data-act="wrong:remove"]').count() === 1, '错题列表丢题');
  });
  await check('首页与统计页说明采用同一正确率口径', async () => {
    await fresh(); await importData({ progress: { 'q-0001': { seen: 2, correct: 1, wrong: 1 } } }); await nav('stats');
    assert(!(await page.locator('#view').textContent()).includes('首页「作答正确率」按作答次数计'), '统计页仍声称首页使用旧口径');
  });
  const summary = { suite: 'full_project', pass: results.filter(x => x.ok).length, fail: results.filter(x => !x.ok).length, results, errors };
  if (process.env.JLX_AUDIT_OUTPUT) fs.writeFileSync(process.env.JLX_AUDIT_OUTPUT, JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary));
  process.exitCode = results.some(x => !x.ok) || errors.length ? 1 : 0;
} finally { await browser.close(); }
