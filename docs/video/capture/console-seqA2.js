const { ouvrir } = require('./pw.js');
const D = '/tmp/saife-video-v1/rec/console/';
const shot = async (page, nom) => { await page.screenshot({ path: D + nom + '.png' }); console.log('->', nom); };
const defile = (page, y) => page.evaluate((y) => document.querySelector('.principal').scrollTo(0, y), y);
(async () => {
  const { ctx, page } = await ouvrir();
  await ctx.addInitScript(() => { try { localStorage.setItem('dedale.analyste', 'Marc N.'); } catch (e) {} });
  await page.goto('http://localhost:5190/?incident=INC-0002', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2500);
  await defile(page, 640); await page.waitForTimeout(400);
  await page.getByRole('button', { name: /Couper l'agent/ }).first().click();
  await page.waitForTimeout(600);
  await page.getByPlaceholder(/En quelques mots/).pressSequentially('Consigne cachée suivie : rapport vers un domaine externe.', { delay: 15 });
  await page.waitForTimeout(300);
  await shot(page, 'a05-motif-saisi');
  await page.locator('.ag-confirmation button, [class*=confirmation] button').filter({ hasText: /Couper l'agent/ }).first().click().catch(async () => {
    const b = page.getByRole('button', { name: /^Couper l'agent$/ });
    await b.last().click();
  });
  await page.waitForTimeout(700);
  await shot(page, 'a06-coupure-cinq-secondes');
  await page.waitForTimeout(6500);
  await shot(page, 'a07-agent-coupe');
  await defile(page, 0); await page.waitForTimeout(800);
  await shot(page, 'a08-incident-apres-coupure-haut');
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
