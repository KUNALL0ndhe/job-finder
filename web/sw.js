// Minimal service worker. Its presence + a fetch handler is what lets Android
// install this as a real app (WebAPK) instead of a plain shortcut. Network-first
// so the shortlist is always fresh, with the last page as an offline fallback.
const CACHE = "jobs-v1";

self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy));
        return resp;
      })
      .catch(() => caches.match(event.request))
  );
});

// --- Web Push: show a notification when the workflow sends new-job alerts ---
self.addEventListener("push", (event) => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch (e) {}
  const title = d.title || "New jobs";
  const body = d.body || "Open to see what's new.";
  const count = d.count || 0;
  event.waitUntil(
    self.registration.showNotification(title, {
      body: body,
      icon: "icon-192.png",
      badge: "icon-192.png",
      tag: "job-update",            // one alert replaces the last, no pile-up
      renotify: true,
      data: { url: "./?r=" + Date.now() }
    }).then(() => {
      if (count && self.navigator && self.navigator.setAppBadge) {
        self.navigator.setAppBadge(count).catch(() => {});
      }
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "./";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cs) => {
      for (const c of cs) { if ("focus" in c) return c.focus(); }
      return self.clients.openWindow(url);
    })
  );
});
