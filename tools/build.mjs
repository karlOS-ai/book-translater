// Builds the standalone PWA in docs/ from src/app.html.
// src/app.html is written as an artifact page (no <html>/<head>/<body>); this wraps it in a full document
// with the manifest, home-screen icons and the service worker, so it can be hosted on any static host
// (e.g. GitHub Pages → "Deploy from branch: main /docs").
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = readFileSync(join(root, 'src/app.html'), 'utf8');
const split = src.indexOf('<div id="app">');
if (split < 0) throw new Error('src/app.html: <div id="app"> not found');
const head = src.slice(0, split).replace(/<meta name="claude:[^>]*>\s*/g, '');
const body = src.slice(split);
// the everyday dictionary (src/core-en.json.gz, from tools/build_dict.py) is embedded in both pages, so a word
// lookup never waits for a download; rarer words still come from docs/dict/
const core = readFileSync(join(root, 'src/core-en.json.gz')).toString('base64');
const coreTag = `<script type="text/plain" id="core-dict">${core}</script>`;
const version = createHash('sha1').update(src).update(core).digest('hex').slice(0, 10);

const html = `<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Vokabeln">
<meta name="theme-color" content="#F2F2F7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#000000" media="(prefers-color-scheme: dark)">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="icons/icon-180.png">
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
${head.trim()}
</head>
<body>
${body.trim()}
${coreTag}
<script>
if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('sw.js?v=${version}').catch(() => {});
</script>
</body>
</html>
`;

const sw = `// Offline cache for the app shell. Translation requests always go to the network.
const CACHE = 'vokabeln-${version}';
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'icons/icon.svg', 'icons/icon-180.png', 'icons/icon-192.png', 'icons/icon-512.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  const isPage = e.request.mode === 'navigate';
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const hit = await cache.match(isPage ? 'index.html' : e.request, { ignoreSearch: isPage });
    const net = fetch(e.request).then(r => { if (r.ok) cache.put(isPage ? 'index.html' : e.request, r.clone()); return r; }).catch(() => null);
    // the page: fresh from the network when it answers quickly, so updates show at once; files: cache first
    // (a 404 — e.g. after the repository was renamed — keeps showing the saved app, so its words stay reachable)
    if (isPage && hit) { const r = await Promise.race([net, new Promise(r => setTimeout(() => r(null), 2500))]); return r && r.ok ? r : hit; }
    return hit || (await net) || new Response('Offline', { status: 503 });
  })());
});
`;

const manifest = {
  name: 'Vokabel-Übersetzer',
  short_name: 'Vokabeln',
  description: 'Englische Wörter übersetzen, automatisch speichern und mit Karteikarten wiederholen.',
  lang: 'de',
  start_url: './',
  scope: './',
  display: 'standalone',
  background_color: '#F2F2F7',
  theme_color: '#F2F2F7',
  icons: [
    { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
    { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
  ],
  share_target: { action: './', method: 'GET', params: { title: 'title', text: 'text', url: 'url' } }
};

mkdirSync(join(root, 'docs/icons'), { recursive: true });
writeFileSync(join(root, 'docs/index.html'), html);
writeFileSync(join(root, 'docs/sw.js'), sw);
writeFileSync(join(root, 'docs/manifest.webmanifest'), JSON.stringify(manifest, null, 2) + '\n');
writeFileSync(join(root, 'docs/.nojekyll'), '');

// claude.ai page: the same app with the embedded dictionary; a page there may not be able to download files.
// Publish build/artifact.html to the existing artifact URL.
mkdirSync(join(root, 'build'), { recursive: true });
writeFileSync(join(root, 'build/artifact.html'), src.trimEnd() + `\n${coreTag}\n`);
console.log('built docs/ and build/artifact.html, version', version, '· embedded dictionary', (core.length / 1e6).toFixed(2), 'MB');
