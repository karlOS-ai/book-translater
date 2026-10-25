// Renders docs/icons/icon.svg to the PNG sizes the manifest and iOS need.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const svg = fs.readFileSync(path.join(__dirname, '../docs/icons/icon.svg'), 'utf8');
  const b = await chromium.launch();
  for (const [size, file, full] of [[180, 'icon-180.png', true], [192, 'icon-192.png', false], [512, 'icon-512.png', false]]) {
    const p = await b.newPage({ viewport: { width: size, height: size } });
    // iOS rounds the corners itself, so the apple-touch-icon gets a square background
    const art = full ? svg.replace(/rx="114"/, 'rx="0"') : svg;
    await p.setContent(`<html><body style="margin:0;background:transparent">${art.replace('<svg ', `<svg width="${size}" height="${size}" `)}</body></html>`);
    await p.screenshot({ path: path.join(__dirname, '../docs/icons', file), omitBackground: true });
    await p.close();
  }
  await b.close();
})();
