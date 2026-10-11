/** 复现返回、空白简答回车及跨页翻题，测试真实交付版按钮与键盘。 */
let chromium;
try { chromium = (await import('../../qa-env/node_modules/playwright/index.mjs')).chromium; }
catch { console.log('[SKIP] 交互回归需要本地Playwright'); process.exit(0); }
import fs from 'node:fs';
import assert from 'node:assert/strict';
if (!fs.existsSync(new URL('../dist/军理刷题.html', import.meta.url))) {
 console.log('[SKIP] 交互回归需要先生成离线产物'); process.exit(0);
}
const browser = await chromium.launch();
const results = [];
try {
 const page = await browser.newPage();
 await page.goto(new URL('../dist/军理刷题.html', import.meta.url).href);
 await page.getByRole('button', { name: '知道了', exact: true }).click();
 async function check(name, fn) { try { await fn(); results.push({ name, pass: true }); } catch(e) { results.push({ name, pass: false, error: String(e) }); } }
 await check('导入导出返回首页', async () => {
  await page.evaluate(() => { location.hash = '#/sync'; });
  await page.waitForTimeout(150);
  await page.locator('#btn-back').click();
  await page.waitForTimeout(150);
  assert.equal(await page.evaluate(() => window.__JLX__.state.route), 'home');
 });
 await page.evaluate(() => { location.hash = '#/home'; });
 await page.waitForTimeout(150);
 await page.locator('[data-act="home:startall"]').click();
 async function fixture(short, i) {
  await page.evaluate(({short,i}) => {
   const s=window.__JLX__.state;
   const ids=short?[s.questions.find(q=>q.type==='short').id]:s.questions.slice(0,210).map(q=>q.id);
   s.sess={ids,i,mode:'practice',order:'seq',res:{},draft:{},perm:{},gridOpen:false,gridPage:1};
  },{short,i});
  await page.locator('[data-act="grid:toggle"]').click();
 }
 await check('空白简答回车查看答案',async()=>{
  await fixture(true,0);
  await page.evaluate(() => document.activeElement.blur());
  await page.keyboard.press('Enter');
  assert(await page.evaluate(()=>{const s=window.__JLX__.state.sess;return !!s.revealedRef?.[s.ids[0]];}));
 });
 await check('答题卡跨100题自动翻页',async()=>{
  await fixture(false,99);
  await page.locator('[data-act="nav:next"]').click();
  assert.equal(await page.evaluate(()=>window.__JLX__.state.sess.gridPage),2);
  assert.equal(await page.locator('.qcell[data-i="100"]').count(),1);
  await page.locator('[data-act="nav:prev"]').click();
  assert.equal(await page.evaluate(()=>window.__JLX__.state.sess.gridPage),1);
 });
 console.log(JSON.stringify(results));

 if(results.some(x=>!x.pass))process.exitCode=1;
} finally { await browser.close(); }
