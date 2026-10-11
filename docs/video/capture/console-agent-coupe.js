// Captures réelles de l'incident « agent coupé » pour la séquence vidéo (beat « agent coupé / Stop »).
// Un vrai incident d'exfiltration ouvert par le parcours réel (orbis.demo --scenario reel) : un agent IA
// lit un mail piégé, suit une consigne cachée, tente d'emporter un faux secret hors d'Orbis Pay ; sAIfe
// retient l'action puis coupe l'agent. On capte la console réelle sur le proxy Vite (5173), qui ajoute
// le jeton analyste côté serveur. Sortie : captures/video-agent-coupe/.
//
//   PROFILS=<dir existant> INCIDENT=INC-0016 node console-agent-coupe.js
//
// Chrome/Chromium headless, profil temporaire, 1600x900 @2 (= 3200x1800, comme les autres captures).
const { ouvrir } = require('./pw.js');
const D = '/Users/akasha/Documents/dedale/captures/video-agent-coupe/';
const INC = process.env.INCIDENT || 'INC-0016';
const shot = async (page, nom) => { await page.screenshot({ path: D + nom + '.png' }); console.log('->', nom); };
const defile = (page, y) => page.evaluate((y) => document.querySelector('.principal').scrollTo(0, y), y);
const versElement = (page, sel) => page.evaluate((sel) => {
  const e = document.querySelector(sel);
  if (!e) return null;
  e.scrollIntoView({ block: 'center' });
  return e.getBoundingClientRect().top;
}, sel);

(async () => {
  require('fs').mkdirSync(D, { recursive: true });
  const { ctx, page } = await ouvrir();
  await ctx.addInitScript(() => { try { localStorage.setItem('dedale.analyste', 'Marc N.'); } catch (e) {} });
  await page.goto('http://localhost:5173/?incident=' + INC, { waitUntil: 'networkidle' });
  await page.waitForTimeout(3500);

  // (c) « Coupé » avec l'incident réel : carte d'incident (badges Critique / Agent arrêté, titre,
  //     « Ce qui s'est passé »). On remonte la carte sous l'en-tête.
  await versElement(page, '.ag-entete, .ag-coque');
  await defile(page, Math.max(0, (await page.evaluate(() => document.querySelector('.principal').scrollTop)) - 60));
  await page.waitForTimeout(500);
  await shot(page, 'c-coupe');

  // Variante : tout en haut (liste + détail visible fraude + carte).
  await defile(page, 0); await page.waitForTimeout(400);
  await shot(page, 'c-coupe-haut');

  // (d) La chaîne scellée des 6 étapes (Lecture -> Instruction -> Intention -> Action -> Décision -> Résultat),
  //     avec le journal intact et les canaris touchés.
  await versElement(page, '.ag-zone-chaine, .ag-maillons');
  await page.waitForTimeout(500);
  await shot(page, 'd-chaine');

  // (b) « sAIfe le retient » : on déplie l'étape Action (« Envoyer un rapport … vers une adresse hors
  //     d'Orbis Pay. sAIfe l'a retenue, puis l'analyste l'a annulée »).
  const ouvert = await page.evaluate(() => {
    const libs = [...document.querySelectorAll('.ag-etape-btn')];
    const cible = libs.find((b) => /Action/.test(b.textContent) && /rapport|retenu|adresse/i.test(b.textContent))
      || libs.find((b) => /Action/.test(b.textContent));
    if (!cible) return null;
    if (cible.getAttribute('aria-expanded') !== 'true') cible.click();
    cible.scrollIntoView({ block: 'center' });
    return cible.textContent.slice(0, 60);
  });
  console.log('étape action :', ouvert);
  await page.waitForTimeout(700);
  await shot(page, 'b-retenu');

  // (a) « Un agent IA lit un mail piégé » : la modale du mail entier, défilée sur la consigne cachée surlignée.
  const btn = page.getByRole('button', { name: /Voir le mail en entier/ });
  if (await btn.count()) {
    await btn.first().click();
    await page.waitForTimeout(900);
    const mark = await page.evaluate(() => {
      const m = document.querySelector('.modale');
      const k = m && (m.querySelector('mark') || m.querySelector('.surligne, [class*=surlign], [class*=consigne]'));
      if (k) { k.scrollIntoView({ block: 'center' }); return (k.className || k.tagName); }
      return null;
    });
    console.log('consigne surlignée :', mark);
    await page.waitForTimeout(600);
    await shot(page, 'a-lit-mail');
    // variante : haut de la modale (l'objet « Rapport de l'assistant Orbis Pay »).
    await page.evaluate(() => { const m = document.querySelector('.modale'); if (m) m.scrollTop = 0; });
    await page.waitForTimeout(400);
    await shot(page, 'a-lit-mail-haut');
    await page.keyboard.press('Escape');
  } else {
    console.log('bouton « Voir le mail en entier » introuvable');
  }

  await ctx.close();
})().catch((e) => { console.error('ERR', e); process.exit(1); });
