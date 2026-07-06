// Network-first service worker: always fresh when online (so updates show
// immediately), falls back to cache when offline. Only handles same-origin GETs
// under /app/ — API POSTs (/grade, /structure/*, /problems/*) always hit the network.
const CACHE = "chemgrader-v1";
const SHELL = [
  "/app/", "/app/index.html",
  "/app/app.js", "/app/app.css", "/app/editor.js", "/app/editor.css", "/app/theme.css",
  "/app/builder.html", "/app/builder.js",
  "/app/manifest.webmanifest", "/app/icon.svg",
  "/app/vendor/react.production.min.js", "/app/vendor/react-dom.production.min.js",
  "/app/vendor/smiles-drawer.min.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return; // never intercept API POSTs
  const url = new URL(req.url);
  if (url.origin !== location.origin || !url.pathname.startsWith("/app/")) return;
  e.respondWith(
    fetch(req)
      .then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return resp;
      })
      .catch(() => caches.match(req).then((r) => r || caches.match("/app/index.html")))
  );
});
