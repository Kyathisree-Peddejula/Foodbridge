/* FoodBridge service worker - offline app shell + last-known API data.
 *
 *  app shell (html/js/wasm/fonts/icons) : precache + stale-while-revalidate
 *  page navigations                     : network first → cached index.html → offline.html
 *  API GET (…/api/…)                    : network first, cached copy when offline (per device, cleared on logout)
 *  API writes (POST/PUT/PATCH/DELETE)   : never cached, always network
 */
const VERSION = 'fb-v1';                         // bump to force every client to refresh the shell
const SHELL = `${VERSION}-shell`;
const RUNTIME = `${VERSION}-runtime`;
const API = `${VERSION}-api`;
const PRECACHE = [
  './', 'index.html', 'offline.html', 'manifest.json', 'favicon.png',
  'icons/Icon-192.png', 'icons/Icon-512.png', 'icons/Icon-maskable-192.png', 'icons/apple-touch-icon.png',
  'flutter_bootstrap.js', 'flutter.js', 'main.dart.js',
];
const API_EXCLUDE = [/\/auth\//, /\/internal\//, /\/pos\/v1\//];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL).then(async (cache) => {
    // cache what exists; a missing optional file must not break installation
    await Promise.all(PRECACHE.map((u) => cache.add(new Request(u, {cache: 'reload'})).catch(() => null)));
  }));
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') self.skipWaiting();
  if (event.data === 'clearApiCache') event.waitUntil(caches.delete(API));
});

const isApi = (url) => /\/api\//.test(url.pathname) && !API_EXCLUDE.some((re) => re.test(url.pathname));

async function networkFirst(request, cacheName, timeoutMs) {
  const cache = await caches.open(cacheName);
  try {
    const response = await Promise.race([
      fetch(request),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), timeoutMs)),
    ]);
    if (response && response.ok) cache.put(request, response.clone());
    return response;
  } catch (err) {
    const hit = await cache.match(request);
    if (hit) return hit;
    throw err;
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(RUNTIME);
  const hit = (await caches.match(request));
  const refresh = fetch(request).then((r) => {
    if (r && (r.ok || r.type === 'opaque')) cache.put(request, r.clone());
    return r;
  }).catch(() => null);
  return hit || (await refresh) || Response.error();
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;                       // writes always go to the network
  const url = new URL(req.url);

  if (req.mode === 'navigate') {                           // SPA routes → index.html when offline
    event.respondWith((async () => {
      try {
        const r = await networkFirst(req, SHELL, 4000);
        // static hosts without SPA rewrites answer 404 for /pickups etc. → serve the app shell instead
        if (r.status === 404) return (await caches.match('index.html')) || r;
        return r;
      } catch (_) {
        return (await caches.match('index.html')) || (await caches.match('./')) || caches.match('offline.html');
      }
    })());
    return;
  }
  if (isApi(url)) {
    // Authorization-bearing GETs are cached per device only; the app clears this cache on logout.
    event.respondWith(networkFirst(req, API, 8000).catch(() => new Response(
      JSON.stringify({detail: 'You are offline and this data has not been loaded before.'}),
      {status: 503, headers: {'Content-Type': 'application/json'}})));
    return;
  }
  if (url.origin === self.location.origin || /fonts\.(gstatic|googleapis)\.com|gstatic\.com\/flutter-canvaskit/.test(url.href)) {
    event.respondWith(staleWhileRevalidate(req));
  }
});
