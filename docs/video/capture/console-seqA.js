const { ouvrir } = require('./pw.js');
const D = '/tmp/saife-video-v1/rec/console/';
const shot = async (page, nom) => { await page.screenshot({ path: D + nom + '.png' }); console.log('->', nom); };
const defile = (page, y) => page.evaluate((y) => document.querySelector('.principal').scrollTo(0, y), y);
(async () => {
  const { ctx, page } = await ouvrir();
  await ctx.addInitScript(() => { try { localStorage.setItem('dedale.analyste', 'Marc N.'); } catch (e) {} });
  await page.goto('http://localhost:5190/?incident=INC-0002', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);
  await shot(page, 'a01-incident-ce-qui-sest-passe');
  await defile(page, 640); await page.waitForTimeout(600);
  await shot(page, 'a02-boite-noire-pretri');
  await page.getByRole('button', { name: /Voir le mail en entier/ }).click();
  await page.waitForTimeout(900);
  await shot(page, 'a03-mail-en-entier');
  // descendre dans la modale jusqu'au passage surligné
  const ok = await page.evaluate(() => {
    const m = document.querySelector('.modale');
    const mark = m && (m.querySelector('mark') || m.querySelector('.surligne, [class*=surlign], [class*=consigne]'));
    if (mark) { mark.scrollIntoView({ block: 'center' }); return mark.className || mark.tagName; }
    return null;
  });
  console.log('surligné :', ok);
  await page.waitForTimeout(600);
  await shot(page, 'a04-consigne-surlignee');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);
  await defile(page, 640); await page.waitForTimeout(400);
  await page.getByRole('button', { name: /Couper l'agent/ }).first().click();
  await page.waitForTimeout(800);
  await shot(page, 'a05-confirmation-couper');
  const boutons = await page.evaluate(() => [...document.querySelectorAll('button, textarea, input')].map(b => (b.tagName + ':' + (b.innerText || b.placeholder || '')).slice(0, 80)).filter(t => t.length > 6));
  console.log(JSON.stringify(boutons));
  await ctx.storageState({ path: '/tmp/saife-video-v1/etat-console.json' });
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
