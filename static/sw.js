// Service worker OilBook.
//
// ДАННЫЕ НЕ КЭШИРУЮТСЯ: страницы приложения и ответы /api (клиенты, склад,
// долги, статистика) всегда берутся с сервера — иначе владелец мог бы
// увидеть устаревшие цифры. Без интернета вместо страницы показывается
// заглушка «нет соединения».
//
// Кэшируются только неизменяемые файлы оформления: иконки, библиотека
// графиков, иконки Font Awesome, шрифты. Они одинаковы для всех и не
// содержат данных, а на слабом интернете именно они долго грузились при
// каждом открытии приложения.

const OFFLINE_CACHE = 'oilbook-offline-v4';
const ASSET_CACHE = 'oilbook-assets-v1';
const OFFLINE_URL = '/static/offline.html';
const KEEP = [OFFLINE_CACHE, ASSET_CACHE];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(OFFLINE_CACHE).then((cache) => cache.add(OFFLINE_URL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => !KEEP.includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// версия в адресе (Chart.js/4.4.0, font-awesome/6.4.0, файлы шрифтов) —
// содержимое никогда не меняется, можно сразу брать из кэша
function isImmutable(url) {
  return url.hostname === 'cdnjs.cloudflare.com' || url.hostname === 'fonts.gstatic.com';
}
// свои иконки/manifest и CSS шрифтов — показываем из кэша, а в фоне обновляем
function isRefreshable(url) {
  if (url.hostname === 'fonts.googleapis.com') return true;
  return url.origin === self.location.origin && url.pathname.startsWith('/static/');
}

async function cacheFirst(request) {
  const cache = await caches.open(ASSET_CACHE);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res && (res.ok || res.type === 'opaque')) cache.put(request, res.clone());
  return res;
}

async function staleWhileRevalidate(event) {
  const cache = await caches.open(ASSET_CACHE);
  const hit = await cache.match(event.request);
  const update = fetch(event.request).then((res) => {
    if (res && (res.ok || res.type === 'opaque')) cache.put(event.request, res.clone());
    return res;
  }).catch(() => hit);
  if (hit) { event.waitUntil(update); return hit; }
  return update;
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE_URL)));
    return;
  }
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (isImmutable(url)) { event.respondWith(cacheFirst(req)); return; }
  if (isRefreshable(url)) { event.respondWith(staleWhileRevalidate(event)); return; }
  // всё остальное (в том числе /api) — напрямую в сеть, без кэша
});
