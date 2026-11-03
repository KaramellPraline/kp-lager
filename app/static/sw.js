/* KP Lager – Service Worker: Offline-Lesen und Offline-Warteschlange für Buchungen.
 * Seiten: zuerst Netz (4 s), sonst die zuletzt gesehene Fassung aus dem Speicher.
 * Formulare (Entnehmen, Einlagern, Umlagern, Inventur …) ohne Netz: in IndexedDB merken und
 * in derselben Reihenfolge senden, sobald wieder Verbindung besteht. */
var VERSION = "kp-lager-__V__";
var SHELL = ["/offline", "/static/style.css?v=__V__", "/static/app.js?v=__V__", "/static/htmx.min.js",
  "/static/jsQR.js", "/static/fonts/fonts.css", "/static/icon-192.png", "/manifest.webmanifest"];
var QUEUE_PATHS = [/^\/items\/\d+\/(take|qty|list|lend|return|zaehlen)$/, /^\/inventur\//, /^\/api\/(take|move|move-batch)$/,
  /^\/drop\/\d+$/, /^\/carry\//, /^\/labels\/queue\//, /^\/n\/\d+\/(items|quickadd)$/, /^\/zu-sortieren\/\d+\/move$/,
  /^\/withdrawals\/\d+\/cancel$/, /^\/projekte\/lines\/\d+\/gather$/, /^\/api\/projects\/\d+\/gather$/];

self.addEventListener("install", function (ev) {
  ev.waitUntil(caches.open(VERSION).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (ev) {
  ev.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== VERSION; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function cleanKey(url) {
  var u = new URL(url);
  u.searchParams.delete("msg"); u.searchParams.delete("undo");
  return u.toString();
}
function timeout(ms) { return new Promise(function (_, rej) { setTimeout(function () { rej(new Error("timeout")); }, ms); }); }

/* --- IndexedDB-Warteschlange ------------------------------------------------------------ */
function db() {
  return new Promise(function (res, rej) {
    var r = indexedDB.open("kp-lager-offline", 1);
    r.onupgradeneeded = function () { r.result.createObjectStore("queue", { keyPath: "id", autoIncrement: true }); };
    r.onsuccess = function () { res(r.result); };
    r.onerror = function () { rej(r.error); };
  });
}
function tx(mode, fn) {
  return db().then(function (d) {
    return new Promise(function (res, rej) {
      var t = d.transaction("queue", mode), out = fn(t.objectStore("queue"));
      t.oncomplete = function () { res(out && out.result !== undefined ? out.result : out); };
      t.onerror = function () { rej(t.error); };
    });
  });
}
function count() { return tx("readonly", function (s) { return s.count(); }); }
function all() { return tx("readonly", function (s) { return s.getAll(); }); }
function notify() {
  return count().then(function (n) {
    return self.clients.matchAll().then(function (cs) { cs.forEach(function (c) { c.postMessage({ type: "queue", count: n }); }); });
  });
}

var flushing = null;
function flush() {
  if (flushing) return flushing;
  flushing = all().then(function (rows) {
    return rows.reduce(function (p, row) {
      return p.then(function (ok) {
        if (!ok) return false;  // Reihenfolge einhalten: beim ersten Netzfehler aufhören
        return fetch(row.url, { method: "POST", body: row.body, headers: { "Content-Type": row.type },
                                credentials: "same-origin", redirect: "follow" })
          .then(function (resp) {
            // 2xx/3xx = angekommen; 4xx = vom Server abgelehnt (z. B. Teil gelöscht) -> verwerfen
            return tx("readwrite", function (s) { return s.delete(row.id); }).then(function () { return resp.status < 500; });
          }).catch(function () { return false; });
      });
    }, Promise.resolve(true));
  }).then(notify).finally(function () { flushing = null; });
  return flushing;
}

function enqueue(req) {
  return req.clone().arrayBuffer().then(function (body) {
    var row = { url: req.url, body: body, type: req.headers.get("Content-Type") || "application/x-www-form-urlencoded", ts: Date.now() };
    return tx("readwrite", function (s) { return s.add(row); });
  }).then(function () {
    if (self.registration.sync) self.registration.sync.register("kp-lager-queue").catch(function () {});
    return notify();
  });
}

function queuedResponse(req) {
  var navigate = req.mode === "navigate";
  if (req.headers.get("HX-Request")) return new Response(null, { status: 204 });  // htmx: nicht tauschen
  if (!navigate) {
    return new Response(JSON.stringify({ ok: true, queued: true, msg: "Offline gespeichert – wird gesendet, sobald Verbindung besteht" }),
                        { headers: { "Content-Type": "application/json" } });
  }
  var back = req.referrer || "/";
  var html = "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>" +
    "<title>Offline gespeichert</title><body style='font-family:system-ui;background:#0B0306;color:#f3e9ec;padding:24px'>" +
    "<h1>Offline gespeichert</h1><p>Die Buchung wird automatisch gesendet, sobald wieder Verbindung besteht.</p>" +
    "<p><a style='color:#ff7a93' href='" + back + "'>Zurück</a></p><script>setTimeout(function(){history.back()},1500)</script>";
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}

self.addEventListener("fetch", function (ev) {
  var req = ev.request, url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.method === "POST") {
    var multipart = (req.headers.get("Content-Type") || "").indexOf("multipart/") === 0;
    if (multipart || !QUEUE_PATHS.some(function (rx) { return rx.test(url.pathname); })) return;
    ev.respondWith(fetch(req.clone()).then(function (resp) { flush(); return resp; })
      .catch(function () { return enqueue(req).then(function () { return queuedResponse(req); }); }));
    return;
  }
  if (req.method !== "GET" || url.pathname.indexOf("/api/") === 0 || url.pathname === "/sw.js") return;
  if (url.pathname.indexOf("/static/") === 0) {
    ev.respondWith(caches.match(req).then(function (hit) {
      return hit || fetch(req).then(function (resp) {
        if (resp.ok) { var copy = resp.clone(); caches.open(VERSION).then(function (c) { c.put(req, copy); }); }
        return resp;
      });
    }));
    return;
  }
  if (req.mode === "navigate" || (req.headers.get("Accept") || "").indexOf("text/html") >= 0) {
    var key = cleanKey(req.url);
    ev.respondWith(Promise.race([fetch(req), timeout(4000)]).then(function (resp) {
      if (resp.ok && resp.type === "basic") { var copy = resp.clone(); caches.open(VERSION).then(function (c) { c.put(key, copy); }); }
      flush();
      return resp;
    }).catch(function () {
      return caches.match(key).then(function (hit) { return hit || caches.match("/offline"); });
    }));
  }
});

self.addEventListener("sync", function (ev) { if (ev.tag === "kp-lager-queue") ev.waitUntil(flush()); });
self.addEventListener("message", function (ev) {
  if (ev.data === "flush") ev.waitUntil(flush());
  if (ev.data === "count") ev.waitUntil(notify());
});
