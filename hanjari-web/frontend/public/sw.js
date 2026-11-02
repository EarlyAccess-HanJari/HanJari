// Bump this version when the offline page or its icon changes.
const CACHE = "hanjari-offline-v2";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(["/offline.html", "/favicon.svg"])));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith("hanjari-offline-") && key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== "GET") return;

  // Live predictions must never be served from a previous visit's cache.
  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(event.request, { cache: "no-store" }));
  } else if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request, { cache: "no-cache" }).catch(() => caches.match("/offline.html")));
  } else if (url.pathname === "/favicon.svg") {
    event.respondWith(caches.match("/favicon.svg").then((cached) => cached || fetch(event.request)));
  }
});
