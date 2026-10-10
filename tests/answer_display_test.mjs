/** 真实题卡回归：原始答案存储不变，乱序后的反馈、解析与回顾一致。 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let chromium;
for (const candidate of [process.env.JLX_PLAYWRIGHT, path.join(ROOT, 'node_modules/playwright/index.mjs'), path.join(ROOT, '../qa-env/node_modules/playwright/index.mjs')].filter(Boolean)) {
  try { chromium = (await import(pathToFileURL(candidate).href)).chromium; if (chromium) break; } catch { /* 尝试下一项本地依赖。 */ }
}
if (!chromium || !fs.existsSync(path.join(ROOT, 'dist/军理刷题.html'))) {
  console.log('[SKIP] 答案显示回归需要 Playwright 和打包产物'); process.exit(0);
}
const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
const assert = (ok, message) => { if (!ok) throw Error(message); };
let checks = 0;
function permutations(a) { return a.length ? a.flatMap((x, i) => permutations(a.filter((_, j) => i !== j)).map(p => [x, ...p])) : [[]]; }
try {
  await page.goto(pathToFileURL(path.join(ROOT, 'dist/军理刷题.html')).href);
  await page.waitForFunction(() => window.__JLX__?.state.questions.length === 1531);
  await page.waitForTimeout(450);
  if (await page.getByRole('button', { name: '知道了', exact: true }).isVisible()) await page.getByRole('button', { name: '知道了', exact: true }).click();
  await page.locator('[data-act="home:startall"]').click();
  // 夹具同时设置内存会话，避免离页写回覆盖。通过生产按钮重绘和作答。
  async function fixture(id, perm, shuffle = true, extra = false) {
    await page.evaluate(({ id, perm, shuffle, extra }) => {
      const s = window.__JLX__.state;
      s.settings.shuffleOptions = shuffle; s.settings.explainOpen = true;
      s.sess = { ids: [id], i: 0, mode: 'practice', order: 'seq', title: '答案显示回归', res: {}, draft: {}, perm: { [id]: perm }, gridOpen: false };
      if (extra) { s.byId[id].explanationParts.reason = 'A、B、C正确；故D；A项。NATO保持原样。'; s.byId[id].explanationParts.note = '选A、B正确'; }
    }, { id, perm, shuffle, extra });
    await page.locator('[data-act="grid:toggle"]').click();
  }
  for (const perm of permutations(['A', 'B', 'C', 'D'])) {
    for (const original of ['A', 'B', 'C', 'D']) {
      await fixture('q-0047', perm);
      await page.locator(`[data-act="ans:pick"][data-k="${original}"]`).click();
      const correct = 'ABCD'[perm.indexOf('D')];
      const picked = 'ABCD'[perm.indexOf(original)];
      const answer = await page.locator('.answer-box').textContent();
      const explanation = await page.locator('.ex-row').first().textContent();
      assert(answer.includes(correct) && explanation.includes(`${correct}、融合发展`), `参考答案或解析错位：${perm}`);
      if (original !== 'D') assert((await page.locator('.verdict').textContent()).includes(`你的答案：${picked}`), `作答反馈错位：${perm}/${original}`);
      assert(await page.evaluate(original => window.__JLX__.state.sess.res['q-0047'].picked === original, original), '显示字母被写回原始作答');
      checks++;
    }
  }
  await fixture('q-0047', ['D', 'A', 'B', 'C'], true, true);
  await page.locator('[data-act="ans:pick"][data-k="D"]').click();
  const explanation = await page.locator('.explain').textContent();
  assert(explanation.includes('B、C、D正确；故A；B项') && explanation.includes('选B、C正确') && explanation.includes('NATO保持原样'), '正文重复映射或提示未映射'); checks++;
  await fixture('q-0047', ['D', 'A', 'B', 'C'], false);
  await page.locator('[data-act="ans:pick"][data-k="A"]').click();
  assert((await page.locator('.verdict').textContent()).includes('你的答案：A') && (await page.locator('.ex-row').first().textContent()).includes('D、融合发展'), '关闭乱序仍被映射'); checks++;
  // 多选解析同样从判分答案生成，四字母循环排列可暴露重复映射。
  const multi = await page.evaluate(() => {
    const q = window.__JLX__.state.questions.find(q => q.type === 'multi' && q.options.length === 4 && q.qa.length >= 2);
    return { id: q.id, qa: q.qa, options: q.options };
  });
  for (const perm of permutations(['A', 'B', 'C', 'D'])) {
    await fixture(multi.id, perm);
    for (const L of multi.qa) await page.locator(`[data-act="ans:pick"][data-k="${L}"]`).click();
    await page.locator('[data-act="ans:submit"]').click();
    const text = await page.locator('.ex-row').first().textContent();
    for (const L of multi.qa) assert(text.includes(`${'ABCD'[perm.indexOf(L)]}、${multi.options['ABCD'.indexOf(L)]}`), '多选解析字母与选项错位');
    checks++;
  }
  await page.locator('[data-nav="home"]:visible').first().click();
  await page.locator('[data-act="exam:new"]').click();
  await page.locator('[data-act="exam:start"]').click();
  await page.evaluate(() => {
    const s = window.__JLX__.state;
    Object.assign(s.exam, { ids: ['q-0047'], i: 0, draft: {}, perm: { 'q-0047': ['D', 'A', 'C', 'B'] } });
  });
  await page.locator('[data-act="grid:toggle"]').click();
  await page.locator('[data-act="ans:pick"][data-k="A"]').click();
  await page.locator('[data-act="exam:submit"]').click();
  await page.locator('#modal-foot button').filter({ hasText: /^交卷$/ }).click();
  assert((await page.locator('#view').textContent()).includes('你的答案：B　|　正确答案：A'), '考试回顾仍混用原始与显示字母'); checks++;
  assert(errors.length === 0, errors.join('\n')); checks++;
  console.log(JSON.stringify({ suite: 'answer_display', pass: checks, fail: 0, errors }));
} finally { await browser.close(); }
