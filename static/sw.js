// Service worker OilBook.
//
// ДАННЫЕ БЕРУТСЯ С СЕРВЕРА: страницы приложения и ответы /api (клиенты, склад,
// долги, статистика) при интернете всегда свежие.
//
// Работа без интернета: копия панели (страница «/») хранится в телефоне и
// открывается, ТОЛЬКО когда сети нет, — чтобы мастер мог внести замену
// (она ждёт в очереди телефона и уходит на сервер сама). Копия обновляется
// при каждом открытии панели с интернетом и удаляется при выходе из аккаунта
// и когда сервер отправляет на вход. Остальные страницы без интернета —
// заглушка «нет соединения».
//
// Кэшируются только неизменяемые файлы оформления: иконки, библиотека
// графиков, иконки Font Awesome, шрифты. Они одинаковы для всех и не
// содержат данных, а на слабом интернете именно они долго грузились при
// каждом открытии приложения.

const OFFLINE_CACHE = 'oilbook-offline-v5';
const ASSET_CACHE = 'oilbook-assets-v2';
const OFFLINE_URL = '/static/offline.html';
const PANEL_CACHE = 'oilbook-panel-v1';
const PANEL_KEY = '/__panel';
const KEEP = [OFFLINE_CACHE, ASSET_CACHE, PANEL_CACHE];

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
// /ocr/v1/ — сканер госномера (движок + модель, ~4,5 МБ): скачивается один
// раз, дальше берётся из кэша телефона; при новой модели меняется v1 → v2
function isImmutable(url) {
  if (url.origin === self.location.origin && url.pathname.startsWith('/ocr/')) return true;
  return url.hostname === 'cdnjs.cloudflare.com' || url.hostname === 'fonts.gstatic.com';
}
// свои иконки/manifest и CSS шрифтов — показываем из кэша, а в фоне обновляем
function isRefreshable(url) {
  if (url.hostname === 'fonts.googleapis.com') return true;
  // manifest.json не кэшируем: по нему телефон рисует заставку при запуске,
  // старая копия из кэша оставляла светлый фон с квадратом
  if (url.pathname === '/static/manifest.json') return false;
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

// панель: «/» и вход из Telegram/ярлыка «/tg»
function isPanelPath(p) { return p === '/' || p === '/tg'; }

async function navigate(req) {
  const url = new URL(req.url);
  if (url.origin === self.location.origin && url.pathname === '/logout') {
    await caches.delete(PANEL_CACHE);
    return fetch(req);
  }
  const panel = url.origin === self.location.origin && isPanelPath(url.pathname);
  let res;
  try {
    res = await fetch(req);
  } catch (e) {
    if (panel) {
      const copy = await (await caches.open(PANEL_CACHE)).match(PANEL_KEY);
      if (copy) return copy;
    }
    return (await caches.match(OFFLINE_URL)) || Response.error();
  }
  if (panel) {
    try {
      const cache = await caches.open(PANEL_CACHE);
      if (res.ok && res.headers.get('X-OB-Panel')) await cache.put(PANEL_KEY, res.clone());
      else if (res.ok) await cache.delete(PANEL_KEY);  // отправили на вход/приветствие — копия больше не наша
    } catch (e) { /* место в телефоне закончилось — просто без копии */ }
  }
  return res;
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.mode === 'navigate') {
    event.respondWith(navigate(req));
    return;
  }
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (isImmutable(url)) { event.respondWith(cacheFirst(req)); return; }
  if (isRefreshable(url)) { event.respondWith(staleWhileRevalidate(event)); return; }
  // всё остальное (в том числе /api) — напрямую в сеть, без кэша
});
