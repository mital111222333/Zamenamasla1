// Service worker для PWA — специально МИНИМАЛЬНЫЙ.
//
// Это приложение работает с живыми бизнес-данными (клиенты, склад,
// долги, статистика) — их НЕЛЬЗЯ кэшировать, иначе владелец точки может
// увидеть устаревшие цифры, думая, что видит актуальные, и принять
// решение на основе неверных данных. Поэтому этот service worker не
// кэширует ни HTML-страницы, ни API-ответы — только показывает простую
// заглушку "нет соединения", если запрос страницы не прошёл вообще без
// интернета. Сам факт наличия активного service worker с обработчиком
// fetch нужен браузеру, чтобы предложить "Установить приложение" —
// это его единственная реальная роль здесь.

const OFFLINE_CACHE = 'oilbot-offline-v1';
const OFFLINE_URL = '/static/offline.html';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(OFFLINE_CACHE).then((cache) => cache.add(OFFLINE_URL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  if (event.request.mode !== 'navigate') return; // не трогаем API/данные, только переходы по страницам
  event.respondWith(
    fetch(event.request).catch(() => caches.match(OFFLINE_URL))
  );
});
