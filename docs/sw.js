const CACHE_NAME = "fonlarca-v1";
const STATIC_ASSETS = ["icon-192.png", "icon-512.png", "apple-touch-icon.png", "logo.jpg", "manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Sayfalar (HTML) her zaman ağdan taze çekilsin - veri günde birkaç kez güncelleniyor,
// eski bir sürüm kullanıcıya cache'den gösterilmesin. Sadece statik ikon/logo dosyaları
// cache'den hızlı yüklensin.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isStatic = STATIC_ASSETS.some((asset) => url.pathname.endsWith(asset));

  if (isStatic) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
  } else {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
  }
});
