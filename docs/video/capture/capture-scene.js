// Capture des états de la scène du virement (fichier local, aucun réseau).
const { ouvrir } = require('./pw.js');
const D = '/tmp/saife-video-v1/rec/scene/';
(async () => {
  const { ctx, page } = await ouvrir();
  await page.goto('file://' + require('path').join(__dirname, 'scene.html'));
  await page.waitForTimeout(500);
  const pose = async (nom, e) => { await page.evaluate(x => window.poser(x), e); await page.waitForTimeout(60); await page.screenshot({ path: D + nom + '.png' }); };
  await pose('m0-boite', { vue: 'mail' });
  await pose('m1-banniere', { vue: 'mail', banniere: true });
  await pose('m2-ouvert', { vue: 'mail', ouvert: true });
  const IBAN = 'FR76 3000 4000 5000 6000 7000 1187', MONT = '41 760,00 €';
  await pose('b0-vide', { vue: 'banque', iban: 0, montant: 0 });
  // frappe : 2 caractères par image pour l'IBAN, 1 pour le montant
  let n = 0;
  for (let i = 0; i <= IBAN.length; i += 2) await pose('t' + String(n++).padStart(3, '0'), { vue: 'banque', iban: i, montant: 0, focus: 'iban' });
  await pose('t' + String(n++).padStart(3, '0'), { vue: 'banque', iban: IBAN.length, montant: 0, focus: 'iban' });
  for (let i = 0; i <= MONT.length; i++) await pose('t' + String(n++).padStart(3, '0'), { vue: 'banque', montant: i, focus: 'montant' });
  await pose('b1-plein', { vue: 'banque' });
  await pose('b2-survol', { vue: 'banque', survol: true });
  await pose('b3-envoye', { vue: 'banque', envoye: true });
  await pose('b4-verifie', { vue: 'banque', popup: 'attente' });
  await pose('b5-retenu', { vue: 'banque', popup: 'retenu' });
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
