// Espace /validation : la finance refuse le virement retenu (backend isolé 8790, Vite 5190).
const { ouvrir } = require('./pw.js');
const D = '/tmp/saife-video-v1/rec/validation/';
require('fs').mkdirSync(D, { recursive: true });
(async () => {
  const { ctx, page } = await ouvrir();
  await page.goto('http://localhost:5190/validation/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: D + 'v0-fiche.png' });
  const zone = page.locator('textarea');
  await zone.evaluate(e => e.scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(400);
  await page.screenshot({ path: D + 'v1-decision.png' });
  const motif = "J'ai appelé Atelier Nord : leur RIB n'a pas changé. Tentative de fraude.";
  await zone.click();
  let n = 0;
  for (let i = 3; i <= motif.length; i += 3) {
    await zone.fill(motif.slice(0, i));
    await page.screenshot({ path: D + 'f' + String(n++).padStart(3, '0') + '.png' });
  }
  await zone.fill(motif);
  const nom = page.locator('input[placeholder="Votre nom"]');
  const sig = 'Claire Dubois';
  for (let i = 1; i <= sig.length; i++) {
    await nom.fill(sig.slice(0, i));
    await page.screenshot({ path: D + 'f' + String(n++).padStart(3, '0') + '.png' });
  }
  await page.getByRole('radio', { name: 'Finance' }).click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: D + 'v2-pret.png' });
  await page.getByRole('button', { name: 'Refuser' }).click();
  await page.waitForTimeout(1800);
  await page.screenshot({ path: D + 'v3-refuse.png' });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  await page.screenshot({ path: D + 'v4-refuse-haut.png' });
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
