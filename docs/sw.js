// Bu service worker artık kullanılmıyor. Tarayıcılarda daha önce kaydolmuş
// olabilecek eski sürümlerin kendini silmesi ve tuttuğu tüm önbelleği
// temizlemesi için buraya bilerek bırakıldı.
self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
      await self.registration.unregister();
      const clientsList = await self.clients.matchAll({ type: 'window' });
      clientsList.forEach((client) => client.navigate(client.url));
    })()
  );
});
