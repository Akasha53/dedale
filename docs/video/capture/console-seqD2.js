const { ouvrir } = require('./pw.js');
const D = '/tmp/saife-video-v1/rec/console/';
(async () => {
  const { ctx, page } = await ouvrir();
  await ctx.addInitScript(() => { try { localStorage.setItem('dedale.analyste', 'Marc N.'); } catch (e) {} });
  await page.goto('http://localhost:5190/?incident=INC-0003', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);
  await page.locator('.integrite').first().hover();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: D + 'd01-journal-intact.png' });
  const titre = await page.locator('.integrite').first().getAttribute('title');
  console.log('INFOBULLE:', titre);
  await page.getByRole('button', { name: /Exporter/ }).click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: D + 'e01-menu-exporter.png' });
  await ctx.close();
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
