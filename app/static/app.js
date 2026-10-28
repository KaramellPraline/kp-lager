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
        if (btn) btn.classList.remove("recording");
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
    if (!btn && !document.querySelector("[data-start-note]")) return;
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
        if (btn) btn.classList.add("recording");
        timer = setInterval(function () { time.textContent = fmt(Math.round((Date.now() - started) / 1000)); }, 1000);
        window.addEventListener("beforeunload", guard);
      }).catch(function () { alert("Kein Zugriff aufs Mikrofon"); });
    }
    if (btn) btn.addEventListener("click", function () { if (rec && rec.state === "recording") rec.stop(); else start(); });
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

  // Auswahl mit „Neu …“ (value "neu") blendet die Eingabefelder im Element data-reveal ein
  document.addEventListener("change", function (ev) {
    if (!ev.target.matches("select[data-reveal]")) return;
    var box = document.getElementById(ev.target.dataset.reveal);
    box.hidden = ev.target.value !== "neu";
    if (!box.hidden) box.querySelector("input").focus();
  });

  // Kopfzeile: Lupe klappt die Suche auf, leer verlassen klappt sie wieder zu
  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("top-search");
    if (!form) return;
    var input = form.querySelector("input");
    form.querySelector(".search-toggle").addEventListener("click", function () {
      if (form.classList.contains("open") && input.value.trim()) { form.submit(); return; }
      form.classList.add("open"); input.focus();
    });
    input.addEventListener("blur", function () {
      setTimeout(function () { if (!input.value.trim()) form.classList.remove("open"); }, 150);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { input.value = ""; input.blur(); }
    });
  });

  // Startseite: Foto zum Hinzufügen (Kamera oder Galerie) mit Vorschau
  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("add-photo-btn"), input = document.getElementById("add-photo");
    if (!btn || !input) return;
    var box = document.getElementById("add-photo-preview"), img = box.querySelector("img");
    btn.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      box.hidden = !f;
      btn.classList.toggle("on", !!f);
      if (f) img.src = URL.createObjectURL(f);
    });
    document.getElementById("add-photo-clear").addEventListener("click", function () {
      input.value = ""; box.hidden = true; btn.classList.remove("on");
    });
  });

  // Startseite: Kategorie CBL blendet Stecker A / Stecker B / Länge ein, Freitext wird optional
  function syncCable(form) {
    var box = form.querySelector("#cable-fields");
    if (!box) return;
    var cat = form.querySelector("input[name=cat]:checked");
    var on = form.querySelector("#add-mode").value === "item" && cat && cat.value === "CBL";
    box.hidden = !on;
    var text = form.querySelector("#quick-home");
    text.required = !on;
    text.placeholder = on ? "optional, frei: z. B. USB A-C 2m" : (text.dataset.ph || text.placeholder);
    if (on) box.querySelector("input").focus();
  }
  document.addEventListener("change", function (ev) {
    if (ev.target.matches(".add-anything input[name=cat]")) syncCable(ev.target.form);
  });

  // Startseite „Hinzufügen“: Teil / Behälter / Typ umschalten
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest(".add-anything .seg button");
    if (!b) return;
    var form = b.closest("form");
    form.querySelectorAll(".seg button").forEach(function (x) { x.classList.toggle("active", x === b); });
    form.querySelector("#add-mode").value = b.dataset.mode;
    form.querySelector("#quick-home").placeholder = b.dataset.ph;
    form.querySelector("#quick-home").dataset.ph = b.dataset.ph;
    syncCable(form);
    var hint = form.querySelector("#add-hint"), submit = form.querySelector("#add-submit .lbl");
    var empty = form.querySelector("#qa-empty");
    if (hint && b.dataset.hint) hint.textContent = b.dataset.hint;
    if (submit && b.dataset.submit) submit.textContent = b.dataset.submit;
    if (empty && b.dataset.empty) empty.textContent = b.dataset.empty;
    form.querySelectorAll("[data-for]").forEach(function (el) {
      el.hidden = el.dataset.for.split(" ").indexOf(b.dataset.mode) < 0;
    });
    form.querySelector("#quick-home").focus();
  });

  // Lange Server-Aktionen (lokale KI): Knopf sperren und Status zeigen
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!form.matches("form[data-busy]")) return;
    var btn = form.querySelector("button");
    if (btn) { btn.disabled = true; btn.textContent = form.dataset.busy; }
  });

  // Sprach-Tab „Teil für Teil“: eine Mikrofon-Sitzung, Abschnitte per Weiter-Knopf,
  // im Text zusätzlich am gesprochenen „weiter“ getrennt (serverseitig).
  document.addEventListener("DOMContentLoaded", function () {
    var start = document.getElementById("cont-start");
    if (!start) return;
    var next = document.getElementById("cont-next"), stop = document.getElementById("cont-stop");
    var state = document.getElementById("cont-state"), log = document.getElementById("cont-log");
    var stream = null, rec = null, finishing = false, pending = 0, total = 0;
    function setButtons(on) { start.disabled = on; next.disabled = !on; stop.disabled = !on; }
    function upload(blob) {
      if (!blob.size) return;
      pending++; state.textContent = "Erkenne …";
      var f = new FormData();
      f.append("audio", blob, "teil.webm");
      fetch("/api/sprache/segment", { method: "POST", body: f })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          log.hidden = false;
          (d.items || []).forEach(function (name) {
            var li = document.createElement("li"); li.className = "item";
            li.innerHTML = '<span class="ic tone-ok">check_circle</span><span class="name"></span>';
            li.querySelector(".name").textContent = name; log.prepend(li); total++;
          });
          if (!d.ok) state.textContent = d.msg;
        })
        .finally(function () {
          pending--;
          if (!pending) state.textContent = (rec ? "Aufnahme läuft · " : "") + total + " Teile erfasst";
        });
    }
    function record() {
      var chunks = [];
      rec = new MediaRecorder(stream);
      rec.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
      rec.onstop = function () {
        upload(new Blob(chunks, { type: rec.mimeType }));
        if (finishing) {
          stream.getTracks().forEach(function (t) { t.stop(); });
          stream = null; rec = null; setButtons(false);
        } else { record(); }
      };
      rec.start();
      state.textContent = "Aufnahme läuft · " + total + " Teile erfasst";
    }
    start.addEventListener("click", function () {
      if (!navigator.mediaDevices || !window.MediaRecorder || !window.isSecureContext) {
        alert("Aufnahme braucht HTTPS (Zertifikat installiert?)."); return;
      }
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
        stream = s; finishing = false; setButtons(true); record();
      }).catch(function () { alert("Kein Zugriff aufs Mikrofon"); });
    });
    next.addEventListener("click", function () { if (rec && rec.state === "recording") rec.stop(); });
    stop.addEventListener("click", function () { finishing = true; if (rec) rec.stop(); });
  });
})();
