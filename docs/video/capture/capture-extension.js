// Page d'avertissement de l'extension (extension/avertissement.html), rendue hors de Chrome :
// copie dans un dossier jetable, script module remplacé par un script classique, réponse du
// service worker simulée (site sosie d'Orbis Pay).
const fs = require('fs'), path = require('path');
const EXT = path.join(__dirname, '..', '..', '..', 'extension');
const DST = '/tmp/saife-video-v1/scene/ext';
fs.mkdirSync(DST, { recursive: true });
for (const f of ['avertissement.html', 'commun.css', 'avertissement.css', 'avertissement.js']) fs.copyFileSync(path.join(EXT, f), path.join(DST, f));
const stub = `<script>
window.chrome = { runtime: { sendMessage: async (m) => m.type === "avertissement" ? {
  trouve: true, titre: "Ce site imite Orbis Pay.", suite: "Ce n'est pas le vrai site.",
  affiche: "orbispay-verification.example", domaine: "orbispay-verification.example",
  imite: "orbispay.example", nom: "Orbis Pay",
  explication: "« orbispay » apparaît dans l'adresse, mais le site appartient à orbispay-verification.example."
} : null } };
</script>
`;
const html = fs.readFileSync(path.join(DST, 'avertissement.html'), 'utf8')
  .replace('<script type="module" src="avertissement.js"></script>', stub + '<script src="avertissement.js"></script>');
fs.writeFileSync(path.join(DST, 'avertissement.html'), html);
const { ouvrir } = require('./pw.js');
(async () => {
  const { ctx, page } = await ouvrir();
  await page.goto('file:///tmp/saife-video-v1/scene/ext/avertissement.html#v1');
  await page.waitForTimeout(800);
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.waitForTimeout(200);
  await page.screenshot({ path: '/tmp/saife-video-v1/rec/scene/s0-site-sosie.png' });
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
