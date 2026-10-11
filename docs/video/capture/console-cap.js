// node cap.js URL nom:scrollY [nom:scrollY ...]  (capture après chargement, défilement de .principal)
const { ouvrir } = require('./pw.js');
const D = '/tmp/saife-video-v1/rec/console/';
(async () => {
  const { ctx, page } = await ouvrir();
  await ctx.addInitScript(() => { try { localStorage.setItem('dedale.analyste', 'Marc N.'); } catch (e) {} });
  await page.goto(process.argv[2], { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);
  for (const a of process.argv.slice(3)) {
    const [nom, y] = a.split(':');
    await page.evaluate((y) => document.querySelector('.principal').scrollTo(0, y), Number(y));
    await page.waitForTimeout(700);
    await page.screenshot({ path: D + nom + '.png' });
    console.log('->', nom);
  }
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
