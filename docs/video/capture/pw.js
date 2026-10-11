// Aide Playwright : Chromium headless, profil temporaire, 1600x900 à l'échelle 2.
// PLAYWRIGHT_MODULE : chemin du paquet playwright (par défaut, celui que `npx playwright` a mis en cache).
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/Users/akasha/.npm/_npx/705bc6b22212b352/node_modules/playwright');
const fs = require('fs');
async function ouvrir(opts = {}) {
  const profil = fs.mkdtempSync((process.env.PROFILS || '/tmp/saife-video-v1') + '/profil-');
  const ctx = await chromium.launchPersistentContext(profil, {
    headless: true,
    args: ['--use-mock-keychain', '--password-store=basic', '--hide-scrollbars', '--font-render-hinting=none'],
    viewport: { width: opts.w || 1600, height: opts.h || 900 },
    deviceScaleFactor: opts.dpr || 2,
    locale: 'fr-FR',
    colorScheme: 'light',
    reducedMotion: 'no-preference',
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  return { ctx, page };
}
module.exports = { ouvrir };
