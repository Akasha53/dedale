const { ouvrir } = require('./pw.js');
(async () => {
  const { ctx, page } = await ouvrir();
  await page.goto('file://' + process.argv[2], { waitUntil: 'load' });
  await page.waitForTimeout(800);
  await page.screenshot({ path: process.argv[3] });
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
