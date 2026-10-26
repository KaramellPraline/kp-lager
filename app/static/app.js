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
    var done = function () { btn.textContent = "Kopiert ✓"; };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(el.value).then(done);
    } else {
      el.select();
      document.execCommand("copy");
      done();
    }
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
        btn.textContent = "…";
        var form = new FormData();
        form.append("audio", new Blob(chunks, { type: rec.mimeType }), "aufnahme.webm");
        fetch("/api/transcribe", { method: "POST", body: form })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.text) { input.value = d.text; input.focus(); } else { alert(d.error || "Nichts erkannt"); }
          })
          .finally(function () { btn.textContent = "🎤"; });
      };
      rec.start();
    }).catch(function () { alert("Kein Zugriff aufs Mikrofon"); });
  });
})();
