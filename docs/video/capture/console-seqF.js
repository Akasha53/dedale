const { ouvrir } = require('./pw.js');
const D = '/tmp/saife-video-v1/rec/console/';
(async () => {
  const { ctx, page } = await ouvrir();
  await ctx.addInitScript(() => { try { localStorage.setItem('dedale.analyste', 'Marc N.'); } catch (e) {} });
  await page.goto('http://localhost:5190/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2500);
  await page.locator('[role=tab], button').filter({ hasText: /^Salariés/ }).first().click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: D + 'f01-salaries-en-direct.png' });
  const t = await page.locator('.principal').innerText();
  console.log('Camille présent :', /Camille/.test(t), '| extrait :', t.slice(0, 600).replace(/\n/g, ' / '));
  await page.locator('button.nav-item').filter({ hasText: 'Mesures' }).click();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: D + 'f02-mesures.png' });
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
