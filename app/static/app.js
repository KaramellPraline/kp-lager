// Kleine Helfer ohne Build-Schritt: Toasts, Kopieren und Spracheingabe.
(function () {
  "use strict";

  // Meldung aus der URL entfernen (Neuladen zeigt sie nicht erneut), Toast ohne Rückgängig ausblenden
  document.addEventListener("DOMContentLoaded", function () {
    var url = new URL(location.href);
    if (url.searchParams.has("msg") || url.searchParams.has("undo")) {
      url.searchParams.delete("msg"); url.searchParams.delete("undo");
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
    var toast = document.querySelector(".toast");
    if (toast) setTimeout(function () { toast.remove(); }, toast.hasAttribute("data-autohide") ? 4000 : 10000);
  });

  // Text eines Feldes kopieren (Zwischenablage-API gibt es nur unter HTTPS -> Fallback)
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("button.copy");
    if (!btn) return;
    var el = document.getElementById(btn.dataset.target);
    var done = function () { btn.textContent = "Kopiert"; };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(el.value).then(done);
    } else {  // Fallback ohne HTTPS: sichtbares Hilfsfeld kurz einblenden
      var tmp = document.createElement("textarea");
      tmp.value = el.value; tmp.style.position = "fixed"; tmp.style.opacity = "0";
      document.body.appendChild(tmp); tmp.select();
      document.execCommand("copy"); tmp.remove();
      done();
    }
  });

  // Schnellauswahl „Wohin“: Favoriten/zuletzt verwendet setzen die Auswahlliste
  function markPicks(select) {
    document.querySelectorAll("button.pick").forEach(function (b) {
      b.classList.toggle("on", b.dataset.id === select.value);
    });
  }
  document.addEventListener("click", function (ev) {
    var pick = ev.target.closest("button.pick");
    if (!pick) return;
    var select = document.getElementById("qa-target");
    select.value = pick.dataset.id;
    markPicks(select);
  });
  document.addEventListener("change", function (ev) {
    if (ev.target.id === "qa-target") markPicks(ev.target);
  });
  document.addEventListener("DOMContentLoaded", function () {
    var select = document.getElementById("qa-target");
    if (select) markPicks(select);
  });

  // Kachel „Eintragen“ auf der Startseite: zum Formular springen und direkt die Aufnahme starten
  document.addEventListener("click", function (ev) {
    var tile = ev.target.closest("a.mic-tile");
    if (!tile) return;
    ev.preventDefault();
    var form = document.getElementById("schnell");
    form.scrollIntoView({ behavior: "smooth", block: "center" });
    var mic = form.querySelector("button.mic");
    if (mic) mic.click(); else document.getElementById(tile.dataset.target).focus();
  });

  // Mikrofon-Knopf: aufnehmen, an /api/transcribe schicken, Text ins Feld schreiben
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("button.mic");
    if (!btn) return;
    var input = document.getElementById(btn.dataset.target);
    if (btn.recorder) { btn.recorder.stop(); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      alert("Mikrofon braucht HTTPS. Alternativ das Mikrofon der Tastatur nutzen.");
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      var chunks = [];
      var rec = new MediaRecorder(stream);
      btn.recorder = rec;
      btn.classList.add("recording");
      rec.ondataavailable = function (e) { chunks.push(e.data); };
      rec.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        btn.recorder = null;
        btn.classList.remove("recording");
        var orig = btn.innerHTML;
        btn.textContent = "…";
        var form = new FormData();
        form.append("audio", new Blob(chunks, { type: rec.mimeType }), "aufnahme.webm");
        fetch("/api/transcribe", { method: "POST", body: form })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.text) { input.value = d.text; input.focus(); } else { alert(d.error || "Nichts erkannt"); }
          })
          .finally(function () { btn.innerHTML = orig; });
      };
      rec.start();
    }).catch(function () { alert("Kein Zugriff aufs Mikrofon"); });
  });

  // Lange Aufnahme (Diktat) aus der Kopfzeile -> /api/notes -> Mehr › Aufnahmen
  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("note-rec");
    if (!btn) return;
    var bar = document.getElementById("rec-bar"), time = document.getElementById("rec-time");
    var rec = null, chunks = [], started = 0, timer = null, keep = true;
    function fmt(sec) { return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0"); }
    function guard(ev) { ev.preventDefault(); ev.returnValue = ""; }
    function finish() {
      clearInterval(timer);
      window.removeEventListener("beforeunload", guard);
      btn.classList.remove("recording");
    }
    function start() {
      if (!navigator.mediaDevices || !window.MediaRecorder || !window.isSecureContext) {
        alert("Aufnahme braucht HTTPS (Zertifikat installiert?)."); return;
      }
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
        chunks = []; keep = true;
        rec = new MediaRecorder(stream);
        rec.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
        rec.onstop = function () {
          stream.getTracks().forEach(function (t) { t.stop(); });
          finish();
          var secs = Math.round((Date.now() - started) / 1000);
          if (!keep) { bar.hidden = true; rec = null; return; }
          time.textContent = "wird erkannt …";
          bar.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
          var form = new FormData();
          form.append("audio", new Blob(chunks, { type: rec.mimeType }), "diktat.webm");
          form.append("duration", secs);
          fetch("/api/notes", { method: "POST", body: form })
            .then(function (r) { return r.json(); })
            .then(function (d) { location.href = "/sprache?msg=" + encodeURIComponent(d.msg) + "#aufnahmen"; })
            .catch(function () { alert("Hochladen fehlgeschlagen"); bar.hidden = true; });
        };
        rec.start(1000);
        started = Date.now();
        bar.hidden = false; time.textContent = "0:00";
        bar.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
        btn.classList.add("recording");
        timer = setInterval(function () { time.textContent = fmt(Math.round((Date.now() - started) / 1000)); }, 1000);
        window.addEventListener("beforeunload", guard);
      }).catch(function () { alert("Kein Zugriff aufs Mikrofon"); });
    }
    btn.addEventListener("click", function () { if (rec && rec.state === "recording") rec.stop(); else start(); });
    document.querySelectorAll("[data-start-note]").forEach(function (b) {
      b.addEventListener("click", function () { if (!(rec && rec.state === "recording")) start(); });
    });
    document.getElementById("rec-stop").addEventListener("click", function () { if (rec) rec.stop(); });
    document.getElementById("rec-cancel").addEventListener("click", function () {
      if (rec && confirm("Aufnahme verwerfen?")) { keep = false; rec.stop(); }
    });
  });

  // Typ-Auswahl: „Neuer Typ …“ blendet das Namensfeld ein
  document.addEventListener("change", function (ev) {
    if (!ev.target.matches("select[data-new-type]")) return;
    var field = ev.target.form.querySelector("input[name=new_type]");
    field.hidden = ev.target.value !== "neu";
    if (!field.hidden) field.focus();
  });
})();
