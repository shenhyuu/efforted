const CACHE = 'zhihen-shell-v4'
const SHELL = ['/', '/backfill', '/lamps', '/timeline', '/manifest.webmanifest', '/icon.svg', '/favicon.ico']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => Promise.allSettled(
    SHELL.map((url) => cache.add(url)),
  )))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))))
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET' || new URL(request.url).pathname.startsWith('/api/')) return
  event.respondWith(fetch(request).then((response) => {
    const copy = response.clone()
    caches.open(CACHE).then((cache) => cache.put(request, copy))
    return response
  }).catch(() => caches.match(request).then((cached) => cached || caches.match('/'))))
})
