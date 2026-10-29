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
    var mic = form.querySelector("button.mic[data-target]");
    if (mic) mic.click(); else document.getElementById(tile.dataset.target).focus();
  });

  // Mikrofon-Knopf: aufnehmen, an /api/transcribe schicken, Text ins Feld schreiben
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("button.mic[data-target]");
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
    var rec = null, chunks = [], started = 0, timer = null, keep = true, lastSecs = 0, lastType = "";
    function upload() {
      time.textContent = "wird gespeichert …";
      bar.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      var form = new FormData();
      form.append("audio", new Blob(chunks, { type: lastType }), "diktat.webm");
      form.append("duration", lastSecs);
      form.append("transcribe", "0");
      fetch("/api/notes", { method: "POST", body: form })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) throw new Error(d.msg);
          chunks = [];
          location.href = "/sprache?msg=" + encodeURIComponent(d.msg) + "#aufnahmen";
        })
        .catch(function () {
          time.textContent = "Speichern fehlgeschlagen";
          var stop = document.getElementById("rec-stop");
          stop.disabled = false; stop.textContent = "Erneut speichern";
        });
    }
    function fmt(sec) { return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0"); }
    function guard(ev) { ev.preventDefault(); ev.returnValue = ""; }
    function finish() {
      clearInterval(timer);
      window.removeEventListener("beforeunload", guard);
      if (btn) btn.classList.remove("recording");
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
          lastSecs = secs; lastType = rec.mimeType;
          upload();
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
    document.getElementById("rec-stop").addEventListener("click", function () {
      if (!rec) return;
      if (rec.state === "inactive") upload(); else rec.stop();
    });
    document.getElementById("rec-cancel").addEventListener("click", function () {
      if (rec && rec.state === "recording" && confirm("Aufnahme verwerfen?")) { keep = false; rec.stop(); }
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
    var other = box.querySelector("input");
    if (other && box.classList.contains("other-plug")) other.required = !box.hidden;
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
    var input = document.getElementById("add-photo"), btns = document.querySelectorAll(".photo-trigger");
    if (!btns.length || !input) return;
    var box = document.getElementById("add-photo-preview"), img = box.querySelector("img");
    function mark(on) { btns.forEach(function (b) { b.classList.toggle("on", on); }); }
    btns.forEach(function (b) { b.addEventListener("click", function () { input.click(); }); });
    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      box.hidden = !f;
      mark(!!f);
      if (f) img.src = URL.createObjectURL(f);
    });
    document.getElementById("add-photo-clear").addEventListener("click", function () {
      input.value = ""; box.hidden = true; mark(false);
    });
  });

  // Startseite: Kategorie mit eigenen Feldern (CBL, PSU) ersetzt das freie Eingabefeld
  function syncCable(form) {
    var free = form.querySelector("#free-row");
    if (!free) return;
    var cat = form.querySelector("input[name=cat]:checked");
    var item = form.querySelector("#add-mode").value === "item";
    var active = null;
    form.querySelectorAll(".spec-fields").forEach(function (box) {
      var on = item && cat && box.dataset.cat === cat.value;
      box.hidden = !on;
      if (on) active = box;
    });
    free.hidden = !!active;
    form.querySelectorAll(".other-plug").forEach(function (o) {
      var sel = form.querySelector('[data-reveal="' + o.id + '"]');
      o.hidden = !(sel && sel.closest(".spec-fields") === active && sel.value === "neu");
      o.querySelector("input").required = !o.hidden;
    });
    form.querySelector("#quick-home").required = !active;
    var hint = form.querySelector("#add-hint"), seg = form.querySelector(".seg button.active");
    if (hint) hint.textContent = active ? active.dataset.hint : (seg ? seg.dataset.hint : hint.textContent);
    return active;
  }
  document.addEventListener("change", function (ev) {
    if (!ev.target.matches(".add-anything input[name=cat]")) return;
    var active = syncCable(ev.target.form);
    if (active) active.querySelector("input").focus();
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
    if (hint && b.dataset.hint && !syncCable(form)) hint.textContent = b.dataset.hint;
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
  // Eurobox: Normmaße zur Auswahl, andere Arten bekommen ein freies Maßfeld
  function syncDims(form) {
    var kind = form.querySelector("select[name=kind]");
    if (!kind || !form.querySelector("[data-dims-for]")) return;
    form.querySelectorAll("[data-dims-for]").forEach(function (l) { l.hidden = l.dataset.dimsFor !== kind.value; });
    form.querySelectorAll("[data-dims-other]").forEach(function (l) { l.hidden = kind.value === "eurobox"; });
    var isEuro = kind.value === "eurobox", sel = form.querySelector("select[name=dims]");
    if (!isEuro && sel) { sel.value = ""; var box = form.querySelector("#dims-new"); if (box) box.hidden = true; }
  }
  document.addEventListener("change", function (ev) {
    if (ev.target.matches("select[name=kind]") && ev.target.form) syncDims(ev.target.form);
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(syncDims);
  });

  // Start: Foto mit lokaler KI auswerten und das Formular vorausfüllen
  function setSelect(form, sel, val) {
    var want = String(val).trim().toLowerCase(), hit = null;
    Array.prototype.forEach.call(sel.options, function (o) { if (o.text.trim().toLowerCase() === want) hit = o; });
    if (hit) { sel.value = hit.value; return; }
    var other = form.querySelector('[name="' + sel.name + '_new"]');
    if (other && sel.querySelector('option[value="neu"]')) {
      sel.value = "neu"; sel.dispatchEvent(new Event("change", { bubbles: true })); other.value = val;
    }
  }
  function fillFromPhoto(form, items) {
    var it = items[0], specs = it.specs || {};
    if (form.querySelector("#add-mode").value !== "item") form.querySelector('.seg button[data-mode=item]').click();
    var radio = form.querySelector('input[name=cat][value="' + it.cat + '"]');
    if (radio) { radio.checked = true; radio.dispatchEvent(new Event("change", { bubbles: true })); }
    form.querySelector("#quick-home").value = items.map(function (i) { return (i.qty ? i.qty + " " : "") + i.name; }).join(", ");
    var box = form.querySelector('.spec-fields[data-cat="' + it.cat + '"]');
    if (box) {
      var put = function (name, val) {
        var el = box.querySelector('[name="' + name + '"]');
        if (!el || !val) return;
        if (el.tagName === "SELECT") setSelect(form, el, val); else el.value = val;
      };
      put("plug_a", specs.plug_a); put("plug_b", specs.plug_b); put("length", specs.length);
      put("volt", specs.volt); put("amp", specs.amp); put("psu_plug", specs.plug); put("psu_input", specs.input);
    }
    var hint = form.querySelector("#add-hint");
    if (hint) hint.textContent = "Von der KI vorgeschlagen (" + items.length + ") – bitte prüfen, dann hinzufügen.";
  }
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest("#add-photo-ai");
    if (!b) return;
    var form = b.closest("form"), input = form.querySelector("#add-photo");
    if (!input.files || !input.files[0]) return;
    var fd = new FormData(); fd.append("photo", input.files[0]);
    var orig = b.innerHTML; b.disabled = true; b.textContent = "KI schaut hin …";
    fetch("/api/foto-erkennen", { method: "POST", body: fd })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok) fillFromPhoto(form, d.items); else alert(d.msg || "Nichts erkannt"); })
      .catch(function () { alert("Auswertung fehlgeschlagen"); })
      .finally(function () { b.disabled = false; b.innerHTML = orig; });
  });
})();
