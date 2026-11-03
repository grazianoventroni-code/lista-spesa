// Service worker minimale: tiene in cache l'interfaccia, i dati arrivano sempre dalla rete.
const CACHE = "spesa-v1";
const FILES = ["./", "index.html", "config.js", "manifest.webmanifest", "icon-192.png", "icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return; // Supabase & co. passano diretti
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
