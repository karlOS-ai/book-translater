// Offline cache for the app shell. Translation requests always go to the network.
const CACHE = 'vokabeln-8989bc25ae';
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
