// node seqB.js prefixe "phrase"  : frappe, agent des règles en direct, Appliquer, règle active
const { ouvrir } = require('./pw.js');
const D = '/tmp/saife-video-v1/rec/console/';
const [prefixe, phrase] = process.argv.slice(2);
let n = 0;
(async () => {
  const { ctx, page } = await ouvrir();
  const shot = async (nom) => { const f = `${prefixe}${String(++n).padStart(2, '0')}-${nom}`; await page.screenshot({ path: D + f + '.png' }); console.log('->', f, new Date().toISOString().slice(11, 23)); };
  await ctx.addInitScript(() => { try { localStorage.setItem('dedale.analyste', 'Marc N.'); } catch (e) {} });
  await page.goto('http://localhost:5190/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2500);
  // centrer le panneau des règles
  await page.evaluate(() => { const z = document.querySelector("section.regles"); const p = document.querySelector(".principal"); p.scrollBy(0, z.getBoundingClientRect().top - 130); });
  await page.waitForTimeout(800);
  const champ = page.locator('#regle-phrase');
  await champ.click();
  await shot('vide');
  const pas = Math.ceil(phrase.length / 6);
  for (let i = 0; i < phrase.length; i += pas) {
    await champ.pressSequentially(phrase.slice(i, i + pas), { delay: 10 });
    await shot('frappe');
  }
  await page.locator('button.regle-btn[type=submit]').click();
  const t0 = Date.now();
  while (Date.now() - t0 < 40000) {
    await page.waitForTimeout(300);
    await page.evaluate(() => { const p = document.querySelector('.principal'); p.scrollTo(0, p.scrollHeight); });
    await shot('agent');
    const fini = await page.locator('.regle-reponse').count();
    if (fini) break;
  }
  await page.waitForTimeout(600);
  await page.evaluate(() => { const p = document.querySelector('.principal'); p.scrollTo(0, p.scrollHeight); });
  await page.waitForTimeout(500);
  await shot('proposition');
  await page.evaluate(() => { const z = document.querySelector("section.regles"); const p = document.querySelector(".principal"); p.scrollBy(0, z.getBoundingClientRect().top - 130); });
  await page.waitForTimeout(500);
  await shot('proposition-haut');
  const txt = await page.locator('section.regles').innerText();
  console.log('PANNEAU:', txt.slice(0, 1500));
  const appliquer = page.locator('.regle-choix button.primaire');
  if (await appliquer.count()) {
    await appliquer.click();
    await page.waitForTimeout(1500);
    await page.evaluate(() => { const p = document.querySelector('.principal'); p.scrollTo(0, p.scrollHeight); });
    await page.waitForTimeout(500);
    await shot('appliquee');
    console.log('APRES:', (await page.locator('section.regles').innerText()).slice(0, 1200));
  }
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
