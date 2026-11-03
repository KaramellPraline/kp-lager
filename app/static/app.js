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
    peek(select);
  }
  // Inhalt des gewählten Behälters unter „Wohin?“ zeigen (ab dem 10. Eintrag „Mehr“)
  function peek(select) {
    var box = document.getElementById("qa-peek");
    if (!box) return;
    if (!select.value) { box.hidden = true; box.innerHTML = ""; return; }
    fetch("/n/" + select.value + "/inhalt").then(function (r) { return r.text(); }).then(function (html) {
      box.innerHTML = html; box.hidden = !html.trim(); collapse(box);
    }).catch(function () { box.hidden = true; });
  }
  // Listen mit data-collapse="9": ab dem 10. Eintrag per Knopf aufklappen
  function collapse(root) {
    root.querySelectorAll("ul[data-collapse]").forEach(function (ul) {
      var limit = parseInt(ul.dataset.collapse, 10), rows = Array.prototype.slice.call(ul.children);
      var old = ul.nextElementSibling;
      if (old && old.classList.contains("more-btn")) old.remove();
      if (rows.length <= limit + 1) { rows.forEach(function (r) { r.hidden = false; }); return; }
      rows.forEach(function (r, i) { r.hidden = i >= limit; });
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "more-btn";
      var more = rows.length - limit, open = false;
      function label() { btn.textContent = open ? "Weniger anzeigen" : "Mehr anzeigen (" + more + ")"; }
      label();
      btn.addEventListener("click", function () {
        open = !open;
        rows.forEach(function (r, i) { r.hidden = !open && i >= limit; });
        label();
      });
      ul.after(btn);
    });
  }
  document.addEventListener("DOMContentLoaded", function () { collapse(document); });
  window.lagerCollapse = collapse;
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
      box.querySelectorAll("input, select").forEach(function (el) { el.disabled = !on; });
      if (on) active = box;
    });
    free.hidden = !!active;
    form.querySelectorAll(".other-plug").forEach(function (o) {
      var sel = form.querySelector('[data-reveal="' + o.id + '"]');
      o.hidden = !(sel && sel.closest(".spec-fields") === active && sel.value === "neu");
      o.querySelector("input").required = !o.hidden;
      o.querySelector("input").disabled = o.hidden;
    });
    form.querySelector("#quick-home").required = !active;
    var hint = form.querySelector("#add-hint"), seg = form.querySelector(".seg button.active");
    if (hint) hint.textContent = active ? active.dataset.hint : (seg ? seg.dataset.hint : hint.textContent);
    return active;
  }
  document.addEventListener("change", function (ev) {
    if (!ev.target.matches(".add-anything input[name=cat]")) return;
    syncCable(ev.target.form);  // kein Auto-Fokus: Tastatur soll nicht ungefragt aufgehen
  });

  // Eingabefeld beim Antippen sichtbar halten (Handy-Tastatur verdeckt sonst das Feld)
  document.addEventListener("focusin", function (ev) {
    var el = ev.target;
    if (!el.matches || !el.matches("input:not([type=checkbox]):not([type=radio]):not([type=hidden]), textarea, select")) return;
    setTimeout(function () { el.scrollIntoView({ block: "center", behavior: "smooth" }); }, 300);
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
  });

  // Behälter: Art (Kacheln oder Liste) -> passende Größen zur Auswahl, Airtight nur bei Boxen
  function kindOf(form) {
    var r = form.querySelector("input[name=kind]:checked"), sel = form.querySelector("select[name=kind]");
    var hid = form.querySelector("input[type=hidden][name=kind]");
    return r ? r.value : (sel ? sel.value : (hid ? hid.value : ""));
  }
  function syncDims(form) {
    var box = form.querySelector("[data-dims]");
    if (!box) return;
    var kind = kindOf(form), kinds = JSON.parse(box.dataset.kinds || "[]");
    var sel = box.querySelector("select"), opts = JSON.parse(sel.dataset.opts || "{}");
    var show = kinds.indexOf(kind) >= 0, keep = sel.value;
    var list = opts[kind] || opts["*"] || [];
    sel.innerHTML = "";
    function add(v, t) { var o = document.createElement("option"); o.value = v; o.textContent = t; sel.appendChild(o); }
    add("", "– keine Angabe –");
    list.forEach(function (d) { add(d, d.replace(/x/g, " × ") + " mm"); });
    add("neu", "Andere Maße …");
    sel.value = list.indexOf(keep) >= 0 || keep === "neu" ? keep : "";
    box.hidden = !show; sel.disabled = !show;
    var air = form.querySelector("[data-airtight]");
    if (air) { air.hidden = !show; air.querySelector("input").disabled = !show; }
    var custom = form.querySelector("#dims-new");
    if (custom) { custom.hidden = !show || sel.value !== "neu"; custom.querySelector("input").disabled = custom.hidden; }
    var nk = form.querySelector("#new-kind");
    if (nk) nk.hidden = kind !== "neu";
  }
  document.addEventListener("change", function (ev) {
    if (ev.target.matches("[name=kind]") && ev.target.form) syncDims(ev.target.form);
    if (ev.target.matches("select[name=dims]") && ev.target.form) syncDims(ev.target.form);
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(syncDims);
    document.querySelectorAll(".add-anything").forEach(syncCable);
  });

})();

/* D30: Erreichbarkeit abfragen; Checkbox/Knopf leuchten und sind nur dann bedienbar */
(function () {
  var els = document.querySelectorAll("[data-d30]");
  if (!els.length) return;
  var KEY = "d30_direct";
  function apply(ok, msg) {
    els.forEach(function (el) {
      el.classList.toggle("on", ok);
      el.title = ok ? "D30 bereit" : (msg || "D30 nicht erreichbar");
      var box = el.querySelector("input[type=checkbox]"), btn = el.matches("button") ? el : el.querySelector("button.d30-btn");
      if (box) {
        box.disabled = !ok;
        if (!ok) box.checked = false;
        else if (!box.dataset.init) {
          box.dataset.init = "1";
          try { box.checked = localStorage.getItem(KEY) === "1"; } catch (e) { /* ohne Speicher */ }
        }
      }
      if (btn) btn.disabled = !ok;
    });
  }
  els.forEach(function (el) {
    var box = el.querySelector("input[type=checkbox]");
    if (box) box.addEventListener("change", function () {
      try { localStorage.setItem(KEY, box.checked ? "1" : "0"); } catch (e) { /* ohne Speicher */ }
    });
  });
  var BRIDGE = "http://127.0.0.1:8765";
  function bridgeStatus() {
    return fetch(BRIDGE + "/status").then(function (r) { return r.json(); })
      .then(function (d) { apply(!!d.available, d.msg); })
      .catch(function () { apply(false, "PC-Bridge nicht gestartet (KP-Lager-Client)"); });
  }
  function poll() {
    if (document.hidden) return;
    fetch("/d30/status").then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.enabled && d.bridge) return bridgeStatus();  // Server ohne Bluetooth: Bridge am PC
        apply(!!d.available, d.msg);
      })
      .catch(function () { apply(false, "Server nicht erreichbar"); });
  }
  poll();
  setInterval(poll, 20000);
  document.addEventListener("visibilitychange", poll);
})();


/* PC-Bridge: Codes aus der Meldung (data-d30-codes) per lokalem Druckdienst auf den D30 drucken */
(function () {
  var BRIDGE = "http://127.0.0.1:8765";
  document.addEventListener("DOMContentLoaded", function () {
    var toast = document.querySelector(".toast[data-d30-codes]");
    if (!toast) return;
    var codes = toast.dataset.d30Codes.split(",").filter(Boolean);
    var label = toast.querySelector("span");
    function say(text) { if (label) label.textContent = text; toast.removeAttribute("data-autohide"); }
    say("Drucke " + codes.length + " Etikett(en) über die PC-Bridge …");
    fetch(BRIDGE + "/print", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ codes: codes })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) throw new Error(d.error || "Druck fehlgeschlagen");
      var f = new FormData(); codes.forEach(function (c) { f.append("code", c); });
      fetch("/d30/printed", { method: "POST", body: f });
      say(d.printed + " Etikett(en) gedruckt");
    }).catch(function (e) {
      say("Nicht gedruckt: " + (e && e.message ? e.message : "PC-Bridge nicht erreichbar") + " – Etiketten bleiben in der Warteschlange.");
    });
  });
})();

/* Anlegen (Katalog): Chips, Namensvorschau, Typ-Suche; Einsatz-Assistent; Baum */
(function () {
  // Chips füllen das zugehörige Feld; Klick auf den gleichen Chip leert es wieder
  document.addEventListener("click", function (ev) {
    var chip = ev.target.closest("button.chip");
    if (!chip) return;
    var input = document.getElementById(chip.dataset.for);
    if (!input) return;
    input.value = input.value === chip.textContent ? "" : chip.textContent;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
  });
  function markChips(form) {
    form.querySelectorAll("button.chip").forEach(function (c) {
      var input = document.getElementById(c.dataset.for);
      c.classList.toggle("on", !!input && input.value === c.textContent);
    });
  }
  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("neu-form");
    if (!form) return;
    var np = document.getElementById("np"), timer = null;
    function preview() {
      markChips(form);
      clearTimeout(timer);
      timer = setTimeout(function () {
        var q = new URLSearchParams({ typ: form.dataset.typ });
        form.querySelectorAll("input[name^=f_]").forEach(function (i) { q.set(i.name, i.value); });
        fetch("/neu/vorschau?" + q.toString()).then(function (r) { return r.json(); })
          .then(function (d) { np.textContent = d.name || "–"; }).catch(function () {});
      }, 120);
    }
    form.addEventListener("input", preview);
    preview();
    var filter = document.getElementById("type-filter");
    if (filter) filter.addEventListener("input", function () {
      var q = filter.value.trim().toLowerCase();
      document.querySelectorAll(".neu-types li a").forEach(function (a) {
        a.parentElement.hidden = !!q && a.dataset.name.indexOf(q) < 0;
      });
      document.querySelectorAll(".neu-types details.grp").forEach(function (g) {
        var hit = !!g.querySelector("li:not([hidden])");
        g.hidden = !!q && !hit;
        if (q && hit) g.open = true;
      });
    });
  });

  // Einsatz-Assistent: freie Zellen je Kasten, Zeilen je Fach
  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("bin-form");
    if (!form) return;
    var info = JSON.parse(form.dataset.info), sugg = JSON.parse(form.dataset.sugg);
    var kasten = document.getElementById("bin-kasten"), pos = document.getElementById("bin-pos");
    var div = document.getElementById("bin-div"), rows = document.getElementById("bin-rows");
    var tpl = document.getElementById("bin-row-tpl");
    function cells() {
      var free = (info[kasten.value] || {}).free || [];
      pos.innerHTML = "";
      free.forEach(function (c) { var o = document.createElement("option"); o.value = c; o.textContent = c; pos.appendChild(o); });
    }
    function slots() {
      var n = parseInt(div.selectedOptions[0].dataset.n, 10), parts = div.value.split("x");
      var cols = parseInt(parts[0], 10);
      rows.innerHTML = "";
      for (var i = 0; i < n; i++) {
        var node = tpl.content.cloneNode(true), row = node.querySelector(".bin-row");
        var label = n === 1 ? "Einsatz" : "Fach " + String.fromCharCode(65 + Math.floor(i / cols)) + (i % cols + 1);
        row.querySelector(".slot").textContent = label;
        var typ = row.querySelector(".r-typ"), v = row.querySelector(".r-var"), q = row.querySelector(".r-qty");
        typ.name = "r" + i + "_typ"; v.name = "r" + i + "_var"; q.name = "r" + i + "_qty";
        var dl = document.createElement("datalist"); dl.id = "dl-r" + i; v.setAttribute("list", dl.id);
        typ.addEventListener("change", function (dlist, sel) { return function () {
          var key = sel.value.split("|")[0]; dlist.innerHTML = "";
          (sugg[key] || []).forEach(function (s) { var o = document.createElement("option"); o.value = s; dlist.appendChild(o); });
        }; }(dl, typ));
        row.appendChild(dl);
        rows.appendChild(node);
      }
    }
    kasten.addEventListener("change", cells);
    div.addEventListener("change", slots);
    cells(); slots();
  });

  // Baum: Zweige beim ersten Aufklappen nachladen
  document.addEventListener("toggle", function (ev) {
    var d = ev.target;
    if (!d.matches || !d.matches("details.twig") || !d.open || d.dataset.loaded) return;
    d.dataset.loaded = "1";
    fetch(d.dataset.src).then(function (r) { return r.text(); }).then(function (html) {
      var box = d.querySelector(".branch");
      box.innerHTML = html;
      if (window.lagerCollapse) window.lagerCollapse(box);
    }).catch(function () { d.dataset.loaded = ""; });
  }, true);
})();


/* Typ-Liste: Scrollposition und aufgeklappte Gruppen bleiben beim Wechsel erhalten */
(function () {
  var KEY_SCROLL = "neu_types_scroll", KEY_OPEN = "neu_types_open";
  function get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function put(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* ohne Speicher */ } }
  document.addEventListener("DOMContentLoaded", function () {
    var list = document.querySelector(".neu-types");
    if (!list) return;
    var open = null;
    try { open = JSON.parse(get(KEY_OPEN) || "null"); } catch (e) { open = null; }
    list.querySelectorAll("details.grp").forEach(function (g) {
      if (open && open.indexOf(g.dataset.g) >= 0) g.open = true;
      g.addEventListener("toggle", function () {
        var names = Array.prototype.filter.call(list.querySelectorAll("details.grp"), function (x) { return x.open; })
          .map(function (x) { return x.dataset.g; });
        put(KEY_OPEN, JSON.stringify(names));
      });
    });
    var y = parseInt(get(KEY_SCROLL) || "0", 10);
    if (y) list.scrollTop = y;
    var active = list.querySelector("a.on");
    if (active && !y) active.scrollIntoView({ block: "nearest" });
    list.addEventListener("scroll", function () { put(KEY_SCROLL, String(list.scrollTop)); }, { passive: true });
    list.addEventListener("click", function (ev) {
      if (ev.target.closest("a")) put(KEY_SCROLL, String(list.scrollTop));
    });
  });
})();

/* Platz-Vorschlag beim Anlegen: Behälter mit ähnlichen Teilen (oder leere Boxen) als Chips */
(function () {
  var box = document.querySelector(".place-sugg");
  if (!box) return;
  var form = box.closest("form"), select = document.getElementById(box.dataset.select), timer = null;
  function query() {
    var p = new URLSearchParams();
    var typ = form.querySelector("input[name=typ]"), cat = form.querySelector("input[name=cat]:checked");
    if (typ) p.set("typ", typ.value); else if (cat) p.set("cat", cat.value);
    form.querySelectorAll("input[name^=f_]").forEach(function (el) { if (el.value) p.set(el.name, el.value); });
    return p.toString();
  }
  function load() {
    fetch("/neu/platz?" + query()).then(function (r) { return r.json(); }).then(function (rows) {
      box.innerHTML = "";
      rows.forEach(function (r) {
        var b = document.createElement("button");
        b.type = "button"; b.className = "chip" + (select && select.value === String(r.id) ? " on" : "");
        b.title = r.reason; b.textContent = r.label + " · " + r.reason;
        b.addEventListener("click", function () {
          if (!select) return;
          select.value = String(r.id); select.dispatchEvent(new Event("change", { bubbles: true }));
          box.querySelectorAll(".chip").forEach(function (c) { c.classList.toggle("on", c === b); });
        });
        box.appendChild(b);
      });
    }).catch(function () { box.innerHTML = ""; });
  }
  form.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(load, 400); });
  form.addEventListener("change", function (ev) { if (ev.target.name === "cat") load(); });
  load();
})();

/* Schnellaktionen für Teile: langer Druck, Rechtsklick oder „⋯“-Knopf öffnet ein Menü */
(function () {
  var ACTIONS = [
    ["Öffnen", null],
    ["1 entnehmen", "/items/{id}/take", { qty: "1" }],
    ["Umlagern (aufnehmen)", "/carry/item/{id}"],
    ["Etikett vormerken", "/labels/queue/item/{id}"],
    ["Auf Einkaufsliste", "/items/{id}/list"],
    ["Inventur: stimmt", "/inventur/item/{id}"],
  ];
  var sheet = null;
  function close() { if (sheet) { sheet.remove(); sheet = null; } }
  function post(url, data) {
    var f = document.createElement("form");
    f.method = "post"; f.action = url;
    Object.keys(data || {}).forEach(function (k) {
      var i = document.createElement("input"); i.type = "hidden"; i.name = k; i.value = data[k]; f.appendChild(i);
    });
    document.body.appendChild(f); f.submit();
  }
  function open(li) {
    close();
    var id = li.dataset.qa, link = li.querySelector("a.name");
    sheet = document.createElement("div");
    sheet.className = "qa-sheet"; sheet.setAttribute("role", "menu");
    var title = document.createElement("div");
    title.className = "qa-title"; title.textContent = link ? link.textContent.trim() : "Teil";
    sheet.appendChild(title);
    ACTIONS.forEach(function (a) {
      var b = document.createElement("button");
      b.type = "button"; b.setAttribute("role", "menuitem"); b.textContent = a[0];
      b.addEventListener("click", function () {
        if (!a[1]) { location.href = "/items/" + id; return; }
        post(a[1].replace("{id}", id), a[2]);
      });
      sheet.appendChild(b);
    });
    var c = document.createElement("button");
    c.type = "button"; c.className = "qa-cancel"; c.textContent = "Abbrechen";
    c.addEventListener("click", close);
    sheet.appendChild(c);
    document.body.appendChild(sheet);
    sheet.querySelector("button[role=menuitem]").focus();
  }
  document.addEventListener("click", function (ev) {
    var more = ev.target.closest("button.qa-more");
    if (more) { ev.preventDefault(); open(more.closest("li[data-qa]")); return; }
    if (sheet && !ev.target.closest(".qa-sheet")) close();
  });
  document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") close(); });
  document.addEventListener("contextmenu", function (ev) {
    var li = ev.target.closest("li[data-qa]");
    if (li && !ev.target.closest("button")) { ev.preventDefault(); open(li); }
  });
  var timer = null, startX = 0, startY = 0, fired = false;
  document.addEventListener("touchstart", function (ev) {
    var li = ev.target.closest("li[data-qa]");
    if (!li || ev.target.closest("button")) return;
    fired = false; startX = ev.touches[0].clientX; startY = ev.touches[0].clientY;
    timer = setTimeout(function () { fired = true; if (navigator.vibrate) navigator.vibrate(15); open(li); }, 500);
  }, { passive: true });
  document.addEventListener("touchmove", function (ev) {
    if (timer && (Math.abs(ev.touches[0].clientX - startX) > 10 || Math.abs(ev.touches[0].clientY - startY) > 10)) {
      clearTimeout(timer); timer = null;
    }
  }, { passive: true });
  document.addEventListener("touchend", function (ev) {
    clearTimeout(timer); timer = null;
    if (fired) { ev.preventDefault(); fired = false; }  // kein Klick auf den Link nach langem Druck
  });
})();

/* Offline: Service Worker registrieren, Hinweis bei gemerkten Buchungen, bei Verbindung senden */
(function () {
  if (!("serviceWorker" in navigator)) return;
  var bar = null;
  function show(n) {
    if (!n) { if (bar) { bar.remove(); bar = null; } return; }
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "offline-bar"; bar.setAttribute("role", "status");
      document.body.appendChild(bar);
    }
    bar.textContent = n + (n === 1 ? " Buchung" : " Buchungen") + " offline gemerkt – " +
      (navigator.onLine ? "wird gesendet …" : "wird gesendet, sobald Verbindung besteht");
  }
  navigator.serviceWorker.addEventListener("message", function (ev) {
    if (ev.data && ev.data.type === "queue") show(ev.data.count);
  });
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").then(function () {
      return navigator.serviceWorker.ready;
    }).then(function (reg) {
      if (reg.active) reg.active.postMessage(navigator.onLine ? "flush" : "count");
    }).catch(function () { /* ohne HTTPS/localhost gibt es keinen Service Worker */ });
  });
  window.addEventListener("online", function () {
    if (navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage("flush");
    document.documentElement.classList.remove("is-offline");
  });
  window.addEventListener("offline", function () { document.documentElement.classList.add("is-offline"); });
  if (!navigator.onLine) document.documentElement.classList.add("is-offline");
})();

/* Etiketten-Layout: Live-Vorschau, Felder einfügen, Zeilen verschieben */
(function () {
  var form = document.getElementById("layout-form");
  if (!form) return;
  var img = document.getElementById("label-preview"), timer = null, last = null;
  function query() {
    var p = new URLSearchParams(new FormData(form));
    p.delete("reset");
    return p.toString();
  }
  function refresh() {
    clearTimeout(timer);
    timer = setTimeout(function () {
      img.src = "/etiketten/typ/" + form.dataset.key + "/vorschau.png?" + query() + "&_=" + Date.now();
    }, 150);
  }
  form.addEventListener("input", refresh);
  form.addEventListener("change", refresh);
  form.addEventListener("focusin", function (ev) {
    if (ev.target.matches("input[name^=t_]")) last = ev.target;
  });
  form.querySelectorAll(".field-chip").forEach(function (b) {
    b.addEventListener("click", function () {
      var target = last || form.querySelector("input[name=t_0]");
      var pos = target.selectionStart == null ? target.value.length : target.selectionStart;
      var tok = b.dataset.token, v = target.value;
      var sep = pos > 0 && v.charAt(pos - 1) !== " " && v.charAt(pos - 1) !== "" ? " " : "";
      target.value = v.slice(0, pos) + sep + tok + v.slice(pos);
      target.focus();
      refresh();
    });
  });
  // Zeile nach oben: Werte mit der Zeile darüber tauschen
  form.querySelectorAll(".line-up").forEach(function (b) {
    b.addEventListener("click", function () {
      var row = b.closest(".layout-line"), prev = row.previousElementSibling;
      if (!prev) return;
      ["t", "w", "a"].forEach(function (k) {
        var a = row.querySelector("[name=" + k + "_" + row.dataset.i + "]");
        var c = prev.querySelector("[name=" + k + "_" + prev.dataset.i + "]");
        var tmp = a.value; a.value = c.value; c.value = tmp;
      });
      refresh();
    });
  });
})();

// M46: Bearbeiten-Symbol öffnet den Bearbeiten-Block; Namenszeile haftet beim Runterscrollen
(function () {
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-open]");
    if (!b) return;
    var d = document.getElementById(b.dataset.open);
    if (d) { d.open = true; d.scrollIntoView({ block: "start", behavior: "smooth" }); }
  });
  document.addEventListener("DOMContentLoaded", function () {
    var mini = document.querySelector(".sticky-mini"), head = document.getElementById("head-card");
    if (!mini || !head || !window.IntersectionObserver) return;
    new IntersectionObserver(function (e) { mini.classList.toggle("show", !e[0].isIntersecting); }).observe(head);
  });
})();

// M46: Sprungleiste im Katalog öffnet die Kategorie und scrollt hin
document.addEventListener("click", function (ev) {
  var a = ev.target.closest("[data-jump]");
  if (!a) return;
  ev.preventDefault();
  var d = document.getElementById(a.dataset.jump);
  if (d) { d.open = true; d.scrollIntoView({ block: "start", behavior: "smooth" }); }
});
