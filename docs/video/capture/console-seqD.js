const { ouvrir } = require('./pw.js');
const D = '/tmp/saife-video-v1/rec/console/';
(async () => {
  const { ctx, page } = await ouvrir();
  await ctx.addInitScript(() => { try { localStorage.setItem('dedale.analyste', 'Marc N.'); } catch (e) {} });
  await page.goto('http://localhost:5190/?incident=INC-0002', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);
  await page.locator('.integrite').first().hover();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: D + 'd01-journal-intact.png' });
  const titre = await page.locator('.integrite').first().getAttribute('title');
  console.log('INFOBULLE:', titre);
  await page.getByRole('button', { name: /Exporter/ }).click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: D + 'e01-menu-exporter.png' });
  const [rapport] = await Promise.all([ctx.waitForEvent('page'), page.getByRole('menuitem', { name: /Rapport/ }).click()]);
  await rapport.setViewportSize({ width: 1600, height: 900 });
  await rapport.waitForLoadState('networkidle');
  await rapport.waitForTimeout(1500);
  await rapport.screenshot({ path: D + 'd02-rapport-haut.png' });
  const h = await rapport.evaluate(() => document.documentElement.scrollHeight);
  console.log('hauteur rapport', h);
  let i = 3;
  for (let y = 700; y < h; y += 700) {
    await rapport.evaluate((y) => window.scrollTo(0, y), y);
    await rapport.waitForTimeout(400);
    await rapport.screenshot({ path: D + `d0${i++}-rapport-suite.png` });
  }
  require('fs').writeFileSync(D + 'rapport.html', await rapport.content());
  // export ECS : on lit le JSON par la même voie que la console (fetch même origine, cookie de session)
  const ecs = await page.evaluate(async () => { const r = await fetch('/api/incidents/INC-0002/export?format=ecs'); return r.ok ? JSON.stringify(await r.json(), null, 2) : 'HTTP ' + r.status; });
  require('fs').writeFileSync('/tmp/saife-video-v1/rec/console/INC-0002-ecs.json', ecs);
  const sigma = await page.evaluate(async () => { const r = await fetch('/api/incidents/INC-0002/export?format=sigma'); return r.ok ? await r.text() : 'HTTP ' + r.status; });
  require('fs').writeFileSync('/tmp/saife-video-v1/rec/console/INC-0002-sigma.yml', sigma);
  const cef = await page.evaluate(async () => { const r = await fetch('/api/incidents/INC-0002/export?format=cef'); return r.ok ? await r.text() : 'HTTP ' + r.status; });
  require('fs').writeFileSync('/tmp/saife-video-v1/rec/console/INC-0002.cef', cef);
  console.log('ecs', ecs.length, 'sigma', sigma.length, 'cef', cef.length);
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
