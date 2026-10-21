/* UAply's service worker (served at /uaply-sw.js, so its scope is the whole site). It makes the site installable (Android's "Install app",
   the Play Store's Trusted Web Activity) and does ONE thing: when a page cannot be loaded because the phone is offline, or because the
   server is restarting (a deploy: the host answers 502, 503 or 504 for a few seconds), it shows the saved "offline / starting up" screen,
   which tries again by itself and opens the page as soon as the server answers.
   What it caches: only that screen and its icon (the "shell"). Never the app's own code (the server sends it with no-store so a deploy is
   seen at once), never /api/ (accounts, applications, payments), never another site. It answers page loads (navigations) and that
   screen's own icon only; every other request (scripts, /api/ calls, images, Google, Stripe) is not touched and goes to the network
   exactly as without it. */
var CACHE = "uaply-shell-v1";      /* change the number whenever uaply-offline.html or the icon changes, so phones fetch the new copy */
var PAGE = "/uaply-offline.html", ICON = "/uaply-icon-192.png", SHELL = [PAGE, ICON];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return c.addAll(SHELL.map(function (u) { return new Request(u, { cache: "reload" }); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf("uaply-") === 0 && k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

/* left alone even when they are page loads: the API (the Google sign-in callback is a page load to /api/auth/google/callback), the
   health check, the Android ownership file, the owner's password-protected pages (the browser's own password prompt must stay as it is),
   and anything on another site */
var OWNER_PAGES = ["/setup", "/outbox", "/feedback"];
function untouched(url) {
  var p = url.pathname;
  return url.origin !== self.location.origin || p === "/api" || p.indexOf("/api/") === 0 || p === "/healthz" || p.indexOf("/.well-known/") === 0 ||
    OWNER_PAGES.indexOf(p) >= 0;
}

function shell(fallback) {
  return caches.match(PAGE, { cacheName: CACHE }).then(function (r) { return r || fallback || Response.error(); });
}

self.addEventListener("fetch", function (e) {
  var req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || untouched(url)) return;
  if (req.mode !== "navigate") {
    /* the screen's own icon, from the network when there is one and from the saved copy when not; every other request is not touched */
    if (url.pathname === ICON && !url.search) e.respondWith(fetch(req).catch(function () { return caches.match(url.pathname, { cacheName: CACHE }).then(function (r) { return r || Response.error(); }); }));
    return;
  }
  e.respondWith(fetch(req).then(function (r) {
    return r.status >= 502 && r.status <= 504 ? shell(r) : r;    /* the host's "bad gateway" while the server restarts */
  }, function () {
    return shell();                                               /* no connection at all */
  }));
});
