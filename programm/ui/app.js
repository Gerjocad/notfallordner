(() => {
  const N = window.NFO, $ = (id) => document.getElementById(id), esc = N.esc;
  document.getElementById("lists").innerHTML = N.datalists();

  // ---------- Verbindung zum Programm ----------
  let TOKEN = "";
  const m = /#t=([\w-]+)/.exec(location.hash);
  if (m) { TOKEN = m[1]; try { sessionStorage.setItem("nfo-token", TOKEN); } catch (e) {} history.replaceState(null, "", "/"); }
  else { try { TOKEN = sessionStorage.getItem("nfo-token") || ""; } catch (e) {} }

  async function api(name, daten) {
    const r = await fetch("/api/" + name, { method: "POST", headers: { "Content-Type": "application/json", "X-Token": TOKEN }, body: JSON.stringify(daten || {}) });
    const a = await r.json().catch(() => ({ ok: false, fehler: "Keine Antwort vom Programm" }));
    if (!a.ok) throw new Error(a.fehler || "Fehler");
    return a.daten;
  }

  // ---------- Zustand ----------
  const S = { status: null, kunden: [], sel: null, kunde: null, tab: "kunde", nfTab: 0, filter: "alle", suche: "", ansicht: "start", ergebnis: null, bekannteNeu: new Set(), erst: true };
  const STATUS = { eingeladen: "Wartet auf Notfallkontakte", eingegangen: "Notfallkontakte eingegangen", erstellt: "Ordner erstellt", manuell: "In Bearbeitung" };
  const datum = (ts) => ts ? new Date(ts * 1000).toLocaleDateString("de-DE") : "";
  const zeit = (ts) => ts ? new Date(ts * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }) : "";
  const isoDe = (iso) => { const d = N.isoToDate(iso); return d ? d.toLocaleDateString("de-DE", { day: "numeric", month: "long", year: "numeric" }) : ""; };

  function toast(text, onClick) {
    const t = $("toast"); t.textContent = text; t.hidden = false;
    t.onclick = () => { t.hidden = true; if (onClick) onClick(); };
    clearTimeout(t._h); t._h = setTimeout(() => { t.hidden = true; }, 6000);
  }
  async function kopieren(text, btn) {
    try { await navigator.clipboard.writeText(text); }
    catch (e) { const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e2) {} ta.remove(); }
    if (btn) { const alt = btn.textContent; btn.textContent = "✓ Kopiert"; setTimeout(() => { btn.textContent = alt; }, 1500); }
  }

  // ---------- Liste ----------
  function passt(k) {
    if (S.suche && !k.name.toLowerCase().includes(S.suche.toLowerCase())) return false;
    if (S.filter === "eingegangen") return k.status === "eingegangen";
    if (S.filter === "eingeladen") return k.status === "eingeladen";
    if (S.filter === "erneuerung") return !!k.erneuerung;
    return true;
  }
  function zeile(k) {
    let d = STATUS[k.status] || k.status;
    if (k.status === "eingegangen" && k.eingang) d += " · " + datum(k.eingang);
    else if (k.status === "erstellt" && k.ordner_erstellt) d += " · " + datum(k.ordner_erstellt);
    else if (k.status === "eingeladen") d += " · " + datum(k.erstellt);
    if (k.hinweis) d = k.hinweis;
    if (k.erneuerung) d += " · Erneuerung " + isoDe(k.erneuerung);
    return d;
  }
  function renderListe() {
    const ks = S.kunden.filter(passt);
    $("liste").innerHTML = ks.length ? ks.map((k) =>
      `<li><button type="button" data-id="${k.id}" class="${k.id === S.sel ? "sel" : ""}"><span class="n">${esc(k.name)}</span>${k.neu ? '<span class="dot" title="Neu"></span>' : "<span></span>"}<span class="d">${esc(zeile(k))}</span></button></li>`
    ).join("") : `<li class="leer">${S.kunden.length ? "Keine Treffer." : "Noch keine Kunden. Mit „+ Neuer Kunde“ den ersten Link erstellen."}</li>`;
    const st = S.status, a = $("abruf");
    if (!st) return;
    if (!st.briefkasten.eingerichtet) { a.className = "abruf err"; a.textContent = "Briefkasten nicht eingerichtet"; }
    else if (st.briefkasten.fehler) { a.className = "abruf err"; a.textContent = st.briefkasten.fehler; }
    else { a.className = "abruf"; a.textContent = st.briefkasten.letzter_abruf ? `Briefkasten geprüft um ${zeit(st.briefkasten.letzter_abruf)} Uhr` : "Briefkasten wird geprüft …"; }
    document.title = st.neu ? `(${st.neu}) Notfallordner` : "Notfallordner";
    $("btnEinst").textContent = st.update && st.update.verfuegbar ? "Einstellungen · Update" : "Einstellungen";
  }
  $("liste").addEventListener("click", (e) => { const b = e.target.closest("[data-id]"); if (b) zeigeKunde(b.dataset.id); });
  $("suche").addEventListener("input", (e) => { S.suche = e.target.value; renderListe(); });
  document.querySelector(".filter").addEventListener("click", (e) => {
    const b = e.target.closest("[data-filter]"); if (!b) return;
    S.filter = b.dataset.filter; document.querySelectorAll(".filter button").forEach((x) => x.classList.toggle("on", x === b)); renderListe();
  });

  async function aktualisieren() {
    try {
      const [st, ks] = await Promise.all([api("status"), api("kunden")]);
      S.status = st; S.kunden = ks;
      const neu = ks.filter((k) => k.neu);
      if (!S.erst) {
        const frisch = neu.filter((k) => !S.bekannteNeu.has(k.id));
        if (frisch.length) toast(frisch.length === 1 ? `Notfallkontakte von ${frisch[0].name} eingegangen` : `${frisch.length} neue Einsendungen eingegangen`, () => zeigeKunde(frisch[0].id));
      }
      S.bekannteNeu = new Set(neu.map((k) => k.id)); S.erst = false;
      // Geöffneter Kunde hat inzwischen neue Daten gesendet -> neu laden
      if (S.ansicht === "kunde" && S.kunde) {
        const li = ks.find((x) => x.id === S.kunde.id);
        if (li && (li.eingang || null) !== (S.kunde.eingang || null)) { await speichernAbbrechen(); await zeigeKunde(S.kunde.id); toast(`Notfallkontakte von ${li.name} eingegangen – Ansicht aktualisiert`); }
      }
      renderListe();
      if (S.ansicht === "start") zeigeStart();
    } catch (e) { $("abruf").className = "abruf err"; $("abruf").textContent = "Keine Verbindung zum Programm"; }
  }
  $("btnAbrufen").onclick = async () => {
    const b = $("btnAbrufen"); b.disabled = true; b.textContent = "Prüfe …";
    try { const r = await api("abrufen"); toast(r.fehler ? r.fehler : r.neu ? `${r.neu} neue Einsendung(en) abgeholt` : "Keine neuen Einsendungen"); }
    catch (e) { toast(e.message); }
    b.disabled = false; b.textContent = "Jetzt prüfen"; aktualisieren();
  };
  $("btnEinst").onclick = () => zeigeEinstellungen();
  $("btnNeu").onclick = () => dialogNeu();

  // ---------- Startansicht ----------
  function einrichtungFertig(st) { return st && st.briefkasten.eingerichtet && st.vorlage && st.berater.name; }
  function zeigeStart() {
    S.ansicht = "start"; S.sel = null;
    const st = S.status;
    if (st && !einrichtungFertig(st)) return zeigeEinstellungen(true);
    const neu = S.kunden.filter((k) => k.neu), ern = S.kunden.filter((k) => k.erneuerung);
    $("main").innerHTML = `<div class="view">
      <h1>Übersicht</h1>
      <div class="grid2">
        <div class="card"><h2>Neue Einsendungen</h2>${neu.length ? `<ul class="issues">${neu.map((k) => `<li><button type="button" data-open="${k.id}">${esc(k.name)}</button> – eingegangen ${datum(k.eingang)}</li>`).join("")}</ul>` : '<p class="hint">Keine neuen Einsendungen.</p>'}</div>
        <div class="card"><h2>Erneuerung Patientenverfügung</h2>${ern.length ? `<ul class="issues">${ern.map((k) => `<li><button type="button" data-open="${k.id}">${esc(k.name)}</button> – ${isoDe(k.erneuerung)}</li>`).join("")}</ul>` : '<p class="hint">In den nächsten 60 Tagen steht keine Erneuerung an.</p>'}</div>
      </div>
      <div class="card"><h2>So geht's</h2>
        <ol class="hint" style="margin:0;padding-left:20px;display:grid;gap:4px">
          <li><b>+ Neuer Kunde</b> klicken und die Daten des Kunden sowie seinen Hausarzt eintragen.</li>
          <li><b>Link für Notfallkontakte</b> erstellen und dem Kunden schicken (E-Mail, WhatsApp).</li>
          <li>Der Kunde trägt nur seine Notfallkontakte ein und sendet sie verschlüsselt ab.</li>
          <li>Die Daten erscheinen hier automatisch (rote Markierung in der Liste).</li>
          <li>Kunde öffnen, prüfen und <b>Notfallordner erstellen</b> klicken. Word und PDF landen im Kundenordner.</li>
        </ol>
      </div>
    </div>`;
    $("main").querySelectorAll("[data-open]").forEach((b) => b.onclick = () => zeigeKunde(b.dataset.open));
  }

  // ---------- Neuer Kunde ----------
  function dialogNeu() {
    const ov = document.createElement("div"); ov.className = "overlay";
    const mitLink = S.status && S.status.briefkasten.eingerichtet;
    ov.innerHTML = `<form class="dialog" id="neuForm"><h2>Neuer Kunde</h2>
      <div class="f"><label for="neuName">Name des Kunden</label><input id="neuName" placeholder="z. B. Max Mustermann" autocomplete="off"></div>
      <p class="hint">Danach tragen Sie die Daten des Kunden ein. ${mitLink ? "Für die Notfallkontakte erstellen Sie einen Link, über den der Kunde sie selbst einträgt." : "Der Briefkasten ist noch nicht eingerichtet: Die Notfallkontakte tragen Sie dann ebenfalls selbst ein."}</p>
      <p id="neuErr" class="hint" style="color:var(--accent);font-weight:700"></p>
      <div class="row" style="justify-content:flex-end">
        <button type="button" id="neuAbbr">Abbrechen</button>
        ${mitLink ? '<button type="button" id="neuLink">Anlegen + Link erstellen</button>' : ""}
        <button type="submit" class="primary" id="neuOhne">Anlegen</button>
      </div></form>`;
    document.body.appendChild(ov);
    const zu = () => ov.remove();
    $("neuName").focus();
    $("neuAbbr").onclick = zu;
    ov.addEventListener("keydown", (e) => { if (e.key === "Escape") zu(); });
    const anlegen = async (link) => {
      const name = $("neuName").value.trim();
      if (!name) { $("neuErr").textContent = "Bitte einen Namen eingeben."; $("neuName").focus(); return; }
      ov.querySelectorAll("button").forEach((b) => b.disabled = true);
      try { const k = await api("kunde_neu", { bezeichnung: name, mit_link: link }); zu(); await aktualisieren(); zeigeKunde(k.id, k.nachricht); }
      catch (e) { $("neuErr").textContent = e.message; ov.querySelectorAll("button").forEach((b) => b.disabled = false); }
    };
    if ($("neuLink")) $("neuLink").onclick = () => anlegen(true);
    $("neuForm").onsubmit = (e) => { e.preventDefault(); anlegen(false); };
  }

  // ---------- Kunde ----------
  let speicherTimer = null;
  async function zeigeKunde(id, nachricht) {
    if (S.assistent && S.kunde && S.kunde.id !== id) { try { await api("assistent_aktion", { aktion: "beenden" }); } catch (e) {} }
    S.ansicht = "kunde"; S.sel = id; S.ergebnis = null; S.tab = "kunde"; S.nfTab = 0;
    try { S.kunde = await api("kunde", { id }); } catch (e) { toast(e.message); return; }
    S.kunde.nachricht = nachricht || null;
    if (S.kunde.neu) { api("gelesen", { id }).then(aktualisieren); }
    renderListe(); renderKunde(); $("main").scrollTop = 0;
  }
  const ctx = () => ({ gebdat: S.kunde.daten.kunde.gebdat });
  const obj = (path) => {
    const d = S.kunde.daten;
    if (path === "kunde") return d.kunde; if (path === "arzt") return d.arzt;
    if (path.startsWith("nf.")) return d.nf[+path.split(".")[1]];
    if (path === "termin.kunde") return d.termin.kunde;
    if (path.startsWith("termin.nf.")) return d.termin.nf[+path.split(".")[2]];
  };
  function probleme() { return N.collectIssues(S.kunde.daten, S.status ? S.status.berater : null); }

  function renderKunde() {
    const k = S.kunde, d = k.daten;
    const tabs = [["kunde", "Kunde"], ["arzt", "Hausarzt"], ["nf", "Notfallkontakte"]];
    let inhalt = "";
    if (S.tab === "kunde") inhalt = N.fieldsHtml("kunde", N.F_KUNDE, d.kunde);
    if (S.tab === "nf") inhalt = `<div class="row">${[0, 1, 2].map((i) => `<button type="button" class="small" data-nf="${i}" ${i === S.nfTab ? 'style="font-weight:700;border-color:var(--ink)"' : ""}>${i + 1}. Kontakt${d.nf[i].vorname || d.nf[i].name ? ": " + esc(d.nf[i].vorname || d.nf[i].name) : ""}</button>`).join("")}</div>` + N.fieldsHtml("nf." + S.nfTab, N.F_NF, d.nf[S.nfTab]);
    if (S.tab === "arzt") inhalt = N.fieldsHtml("arzt", N.F_ARZT, d.arzt);
    const linkHtml = k.link ? `<div class="linkbox"><h3>Link für die Notfallkontakte von ${esc(k.name)}</h3>
        <code id="linkText">${esc(k.link)}</code>
        <div class="row"><button type="button" id="kopLink">Link kopieren</button>${k.nachricht ? '<button type="button" id="kopNachr">Nachricht mit Link kopieren</button>' : ""}<button type="button" id="linkNeu" class="small">Neuen Link erstellen</button></div>
        ${k.nachricht ? `<p class="hint" style="white-space:pre-line">${esc(k.nachricht)}</p>` : '<p class="hint">Der Kunde hat seine Notfallkontakte noch nicht gesendet. Der Link kann nur einmal verwendet werden.</p>'}</div>` : "";
    const neuHtml = k.status === "eingegangen" ? `<div class="banner neu"><span>Notfallkontakte vom Kunden eingegangen am ${datum(k.eingang)} um ${zeit(k.eingang)} Uhr. Bitte prüfen.</span></div>` : "";
    const erg = S.ergebnis;
    const ergHtml = erg ? `<div class="card"><h2>Notfallordner erstellt</h2><div class="result">
        <div class="row"><button type="button" data-oeffne="${esc(erg.word)}">Word öffnen</button>${erg.pdf ? `<button type="button" data-oeffne="${esc(erg.pdf)}" class="primary">PDF öffnen</button>` : ""}<button type="button" data-oeffne="${esc(erg.ordner)}">Ordner öffnen</button></div>
        <p class="hint">${erg.felder} Felder ausgefüllt. Gespeichert in ${esc(erg.ordner)}${erg.pdf_mit ? ` · PDF erstellt mit ${esc(erg.pdf_mit)}` : ""}</p>
        ${erg.pdf_fehler ? `<p class="banner err">${esc(erg.pdf_fehler)} Die Word-Datei ist trotzdem fertig.</p>` : ""}
        ${erg.unbekannt.length ? `<p class="hint">Unbekannte Felder in der Vorlage: ${esc(erg.unbekannt.join(", "))}</p>` : ""}</div></div>` : "";

    $("main").innerHTML = `<div class="view">
      <div class="head"><div><h1>${esc(k.name)}</h1><div class="meta"><span class="chip ${k.status}">${STATUS[k.status] || k.status}</span>${k.hinweis ? `<span class="chip warn">${esc(k.hinweis)}</span>` : ""}${k.erneuerung ? `<span class="chip warn">Erneuerung ${isoDe(k.erneuerung)}</span>` : ""}<span class="hint" id="gespeichert"></span></div></div>
        <div class="row">
          ${k.status !== "eingeladen" && S.status && S.status.briefkasten.eingerichtet ? `<button type="button" id="linkNeu2">${k.eingang ? "Kontakte erneut anfragen" : "Link für Notfallkontakte"}</button>` : ""}
          <button type="button" id="btnCrm" title="Stammdaten Feld für Feld aus dem CRM kopieren">Aus CRM übernehmen</button>
          ${k.ordner ? '<button type="button" id="btnOrdner">Ordner öffnen</button>' : ""}
          <button type="button" class="primary" id="btnErstellen">Notfallordner erstellen</button>
        </div></div>
      ${S.assistent ? '<div class="banner ok"><span><b>Kopier-Assistent läuft.</b> Markieren Sie im CRM das angezeigte Feld und drücken Sie Strg+C – die Werte erscheinen hier automatisch.</span></div>' : ""}
      ${neuHtml}${linkHtml}${ergHtml}
      <div class="checkline" id="checkLine"></div>
      <ul class="issues" id="issues" hidden></ul>
      <div class="card">
        <div class="tabs" role="tablist">${tabs.map(([id, l]) => `<button type="button" role="tab" data-tab="${id}" aria-selected="${S.tab === id}">${l}</button>`).join("")}</div>
        <fieldset id="formular" ${S.assistent ? "disabled" : ""} style="border:0;padding:0;margin:0;min-width:0">${inhalt}</fieldset>
      </div>
      <div class="row" style="justify-content:space-between">
        <span class="hint">Änderungen werden automatisch gespeichert.</span>
        <div class="row"><button type="button" class="small danger" id="btnLoeschen">Kunde löschen</button></div>
      </div>
    </div>`;
    document.querySelectorAll("#formular input[data-key]").forEach((el) => { if (el.dataset.path && !el.dataset.path.startsWith("termin")) N.showCheck(el, true, ctx()); });
    pruefzeile();

    const m2 = $("main");
    m2.querySelectorAll("[data-tab]").forEach((b) => b.onclick = () => { S.tab = b.dataset.tab; renderKunde(); });
    m2.querySelectorAll("[data-nf]").forEach((b) => b.onclick = () => { S.nfTab = +b.dataset.nf; renderKunde(); });
    m2.querySelectorAll("[data-oeffne]").forEach((b) => b.onclick = () => api("oeffnen", { pfad: b.dataset.oeffne }).catch((e) => toast(e.message)));
    if ($("btnOrdner")) $("btnOrdner").onclick = () => api("oeffnen", { pfad: k.ordner }).catch((e) => toast(e.message));
    if ($("kopLink")) $("kopLink").onclick = (e) => kopieren(k.link, e.target);
    if ($("kopNachr")) $("kopNachr").onclick = (e) => kopieren(k.nachricht, e.target);
    const neuerLink = async () => { try { const r = await api("link_neu", { id: k.id }); S.kunde = r; renderKunde(); aktualisieren(); toast("Neuer Link erstellt. Der alte Link funktioniert nicht mehr."); } catch (e) { toast(e.message); } };
    if ($("linkNeu")) $("linkNeu").onclick = neuerLink;
    if ($("linkNeu2")) $("linkNeu2").onclick = neuerLink;
    $("btnLoeschen").onclick = (e) => {
      const b = e.target;
      if (!b.dataset.armed) { b.dataset.armed = "1"; b.textContent = "Wirklich löschen? Nochmal klicken"; setTimeout(() => { delete b.dataset.armed; b.textContent = "Kunde löschen"; }, 4000); return; }
      api("kunde_loeschen", { id: k.id }).then(() => { toast("Kunde gelöscht. Die Dateien im Kundenordner bleiben erhalten."); aktualisieren(); zeigeStart(); }).catch((x) => toast(x.message));
    };
    $("btnErstellen").onclick = () => erstellen(false);
    $("btnCrm").onclick = () => assistentStarten();
  }

  function pruefzeile() {
    const p = probleme(), line = $("checkLine"), ul = $("issues");
    if (!line) return p;
    if (!p.length) { line.className = "checkline ok"; line.textContent = "✓ Alle Pflichtfelder ausgefüllt, keine Fehler"; ul.hidden = true; }
    else {
      const inv = p.filter((x) => x.kind === "invalid").length, mis = p.length - inv;
      line.className = "checkline warn";
      line.textContent = [inv ? `${inv} Fehler` : "", mis ? `${mis} Pflichtfeld${mis === 1 ? "" : "er"} leer` : ""].filter(Boolean).join(" · ") + " – Liste anzeigen";
      line.style.cursor = "pointer";
      line.onclick = () => { ul.hidden = !ul.hidden; };
      ul.innerHTML = p.map((x, i) => `<li><button type="button" data-issue="${i}">${esc(x.text)}</button> – ${esc(x.why)}</li>`).join("");
      ul.querySelectorAll("[data-issue]").forEach((b) => b.onclick = () => springe(p[+b.dataset.issue]));
    }
    return p;
  }
  function springe(x) {
    if (x.path === "berater") return zeigeEinstellungen();
    S.tab = x.path === "kunde" ? "kunde" : x.path === "arzt" ? "arzt" : "nf";
    if (x.tab != null) S.nfTab = x.tab;
    renderKunde();
    const el = document.getElementById("in-" + x.path.replace(/\./g, "-") + "-" + x.k);
    if (el) { el.scrollIntoView({ block: "center" }); el.focus(); }
  }

  async function erstellen(trotzdem) {
    const p = probleme();
    if (p.length && !trotzdem) {
      $("issues").hidden = false;
      const line = $("checkLine");
      line.innerHTML = `Es gibt noch ${p.length} offene Punkte. <button type="button" class="small" id="trotzdem">Trotzdem erstellen</button>`;
      $("trotzdem").onclick = (e) => { e.stopPropagation(); erstellen(true); };
      return;
    }
    const b = $("btnErstellen"); b.disabled = true; b.textContent = "Wird erstellt …";
    try {
      await speichernJetzt();
      S.ergebnis = await api("ordner_erstellen", { id: S.kunde.id });
      const erg = S.ergebnis;
      S.kunde = await api("kunde", { id: S.kunde.id });
      renderKunde(); aktualisieren();
      toast(erg.pdf ? "Notfallordner als Word und PDF erstellt" : "Word-Datei erstellt" + (erg.pdf_fehler ? " (ohne PDF)" : ""));
    } catch (e) { toast(e.message); b.disabled = false; b.textContent = "Notfallordner erstellen"; }
  }

  // ---------- Kopier-Assistent ----------
  let assTimer = null, assVersion = -1;
  async function assistentStarten() {
    try { await speichernJetzt(); } catch (e) {}
    let s;
    try { s = await api("assistent_start", { id: S.kunde.id }); } catch (e) { toast(e.message); return; }
    S.assistent = true; S.tab = "kunde"; assVersion = -1;
    if (!s.eigenes_fenster) {
      // kein eigenes Fenster (z. B. im Browser): Assistent schwebend einblenden
      const f = document.createElement("iframe");
      f.id = "assFrame"; f.src = "assistent.html#t=" + TOKEN; f.title = "Kopier-Assistent";
      f.style.cssText = "position:fixed;right:20px;bottom:20px;width:390px;height:560px;border:1px solid var(--line);border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.3);z-index:45;background:var(--surface)";
      document.body.appendChild(f);
    }
    renderKunde();
    clearInterval(assTimer);
    assTimer = setInterval(assistentVerfolgen, 600);
  }
  async function assistentVerfolgen() {
    let s; try { s = await api("assistent_status"); } catch (e) { return; }
    if (s.version !== assVersion && S.kunde && s.kid === S.kunde.id) {
      assVersion = s.version;
      S.kunde = Object.assign(await api("kunde", { id: S.kunde.id }), { nachricht: S.kunde.nachricht });
      renderKunde();
    }
    if (!s.aktiv) {
      clearInterval(assTimer); S.assistent = false;
      const f = $("assFrame"); if (f) setTimeout(() => f.remove(), 1200);
      if (S.kunde) { S.kunde = Object.assign(await api("kunde", { id: S.kunde.id }), { nachricht: S.kunde.nachricht }); renderKunde(); }
      toast("Stammdaten aus dem CRM übernommen – bitte kurz prüfen");
    }
  }
  window.addEventListener("message", (e) => { if (e.data === "assistent-zu") { const f = $("assFrame"); if (f) f.remove(); } });

  async function speichernAbbrechen() { clearTimeout(speicherTimer); speicherTimer = null; }
  async function speichernJetzt() {
    clearTimeout(speicherTimer); speicherTimer = null;
    if (!S.kunde) return;
    let r;
    try { r = await api("kunde_speichern", { id: S.kunde.id, daten: S.kunde.daten, stand: S.kunde.eingang }); }
    catch (e) {
      if (e.message === "ASSISTENT_AKTIV") return;
      if (e.message === "NEUE_DATEN") { toast("Der Kunde hat gerade seine Notfallkontakte gesendet. Die Ansicht wurde aktualisiert."); await zeigeKunde(S.kunde.id); return; }
      throw e;
    }
    if ($("gespeichert")) $("gespeichert").textContent = "Gespeichert " + zeit(Date.now() / 1000);
    S.kunde.name = r.name;
    const li = S.kunden.find((x) => x.id === r.id); if (li) { Object.assign(li, r); renderListe(); }
  }
  $("main").addEventListener("input", (e) => {
    const el = e.target; if (!el.dataset || !el.dataset.path || S.ansicht !== "kunde") return;
    obj(el.dataset.path)[el.dataset.key] = el.value;
    if (!el.dataset.path.startsWith("termin")) N.showCheck(el, false, ctx());
    if (el.dataset.path === "kunde" && el.dataset.key === "gebdat" && $("in-kunde-svnr")) N.showCheck($("in-kunde-svnr"), true, ctx());
    pruefzeile();
    if ($("gespeichert")) $("gespeichert").textContent = "…";
    clearTimeout(speicherTimer); speicherTimer = setTimeout(() => speichernJetzt().catch((x) => toast(x.message)), 600);
  });
  $("main").addEventListener("focusout", (e) => {
    const el = e.target; if (!el.dataset || !el.dataset.path || el.dataset.path.startsWith("termin")) return;
    if (S.ansicht === "kunde" || S.ansicht === "einst") {
      const n = N.tidyValue(el.dataset.key, el.value);
      if (n !== el.value) { el.value = n; el.dispatchEvent(new Event("input", { bubbles: true })); }
      N.showCheck(el, true, S.ansicht === "kunde" ? ctx() : {});
      if (S.ansicht === "kunde") pruefzeile();
    }
  });

  // ---------- Einstellungen ----------
  async function zeigeEinstellungen(ersteinrichtung) {
    S.ansicht = "einst"; S.sel = null; renderListe();
    const st = S.status = await api("status");
    const b = st.berater;
    const schritt = (ok, n, titel, text) => `<div class="step ${ok ? "done" : ""}"><span class="num">${ok ? "✓" : n}</span><div><b>${titel}</b><p class="hint">${text}</p></div><span class="chip ${ok ? "erstellt" : "warn"}">${ok ? "erledigt" : "offen"}</span></div>`;
    $("main").innerHTML = `<div class="view">
      <h1>${ersteinrichtung ? "Willkommen! Einmalige Einrichtung" : "Einstellungen"}</h1>
      <div class="card steps">
        ${schritt(!!b.name, 1, "Ihre Beraterdaten", "Erscheinen im Notfallordner und im Kundenformular.")}
        ${schritt(st.briefkasten.eingerichtet, 2, "Briefkasten verbinden", "Damit Kunden ihre Daten online eintragen können.")}
        ${schritt(!!st.vorlage, 3, "Word-Vorlage wählen", "Ihre Datei „02_Notfallordner_2.5_VornameNachname.docx“.")}
      </div>

      <div class="card"><h2>1. Ihre Beraterdaten</h2>
        ${N.fieldsHtml("berater", N.F_BERATER, b)}
        <div class="f"><label for="ds">Datenschutzhinweis im Kundenformular (optional)</label><textarea id="ds" placeholder="Leer lassen für: „Verantwortlich für die Verarbeitung ist [Ihr Name], [Ihre E-Mail].“">${esc(st.datenschutz || "")}</textarea></div>
        <div class="row"><button type="button" class="primary" id="berSpeichern">Beraterdaten speichern</button><span class="hint" id="berMsg"></span></div>
      </div>

      <div class="card"><h2>2. Briefkasten</h2>
        <p class="hint">Adresse und Zugangsschlüssel Ihres Cloudflare-Briefkastens (siehe Einrichtungsanleitung). Die Kundendaten liegen dort nur verschlüsselt und nur bis zur Abholung.</p>
        <div class="fields">
          <div class="f"><label for="bkAdr">Adresse</label><input id="bkAdr" value="${esc(st.briefkasten.adresse)}" placeholder="https://notfallordner.IHRNAME.workers.dev"><small class="msg"></small></div>
          <div class="f"><label for="bkTok">Zugangsschlüssel</label><input id="bkTok" type="password" placeholder="${st.briefkasten.eingerichtet ? "gespeichert – nur zum Ändern eingeben" : "aus der Einrichtung"}" autocomplete="off"><small class="msg"></small></div>
        </div>
        <div class="row"><button type="button" class="primary" id="bkVerb">Verbinden und testen</button><button type="button" id="bkGen">Neuen Zugangsschlüssel erzeugen</button><span class="hint" id="bkMsg">${st.briefkasten.eingerichtet ? "✓ Verbunden" : ""}</span></div>
        <div class="linkbox" id="bkGenBox" hidden><b>Ihr neuer Zugangsschlüssel</b><code id="bkGenText"></code>
          <div class="row"><button type="button" id="bkGenKop">Kopieren</button></div>
          <p class="hint">Diesen Schlüssel bei Cloudflare als Geheimnis <b>ADMIN_TOKEN</b> eintragen (siehe Anleitung, Schritt 4). Er steht schon im Feld oben – danach hier auf „Verbinden und testen“ klicken.</p></div>
      </div>

      <div class="card"><h2>3. Word-Vorlage</h2>
        <p class="hint">${st.vorlage ? `Aktuell: <b>${esc(st.vorlage.name)}</b> · ${st.vorlage.felder} Serienbrieffelder` : "Noch keine Vorlage gewählt."}</p>
        <div class="row"><label class="filebtn">Word-Vorlage wählen …<input type="file" id="vorlIn" accept=".docx"></label><span class="hint" id="vorlMsg"></span></div>
      </div>

      <div class="grid2">
        <div class="card"><h2>Sicherung erstellen</h2>
          <p class="hint">Speichert alle Kunden, Einstellungen und die Vorlage in einer mit Passwort verschlüsselten Datei. Legen Sie sie z. B. auf einen USB-Stick. Ohne Passwort lässt sie sich nicht öffnen.</p>
          <div class="f"><label for="sichPw">Passwort (mind. 8 Zeichen)</label><input id="sichPw" type="password" autocomplete="new-password"></div>
          <div class="row"><button type="button" id="sichBtn">Sicherung erstellen</button><span class="hint" id="sichMsg"></span></div>
        </div>
        <div class="card"><h2>Sicherung wiederherstellen</h2>
          <p class="hint">Ersetzt alle Daten in diesem Programm durch die Sicherung, z. B. auf einem neuen PC.</p>
          <div class="f"><label for="wiedPw">Passwort der Sicherung</label><input id="wiedPw" type="password" autocomplete="off"></div>
          <div class="row"><label class="filebtn">Sicherungsdatei wählen …<input type="file" id="wiedIn" accept=".nfo"></label><span class="hint" id="wiedMsg"></span></div>
        </div>
      </div>

      <div class="card" id="updKarte"><h2>Programm-Update</h2>
        <p class="hint">Installierte Version: <b>${esc(st.version)}</b>${st.update && st.update.verfuegbar ? ` · <b style="color:var(--accent)">Version ${esc(st.update.neueste)} verfügbar</b>` : ""}</p>
        <div class="row"><button type="button" id="updPruefen">Nach Updates suchen</button><button type="button" class="primary" id="updInstall" ${st.update && st.update.verfuegbar ? "" : "hidden"}>Jetzt aktualisieren</button><span class="hint" id="updMsg"></span></div>
        <p class="hint" id="updHinweise" style="white-space:pre-line">${st.update && st.update.verfuegbar ? esc(st.update.hinweise) : ""}</p>
        <p class="hint">Ihre Kunden und Einstellungen bleiben beim Update erhalten. Das Programm startet danach von selbst neu.</p>
      </div>

      <div class="card"><h2>Info</h2>
        <p class="hint">PDF-Erstellung: <b>${st.pdf ? esc(st.pdf) : "nicht verfügbar – Microsoft Word oder LibreOffice installieren"}</b></p>
        <p class="hint">Kundenordner werden gespeichert in: <b>${esc(st.ausgabe)}</b></p>
        <div class="row"><button type="button" class="small" id="ausgOeffnen">Ordner öffnen</button></div>
      </div>
    </div>`;
    document.querySelectorAll("#main input[data-path='berater']").forEach((el) => N.showCheck(el, true, {}));

    $("berSpeichern").onclick = async () => {
      const ber = {}; document.querySelectorAll("#main input[data-path='berater']").forEach((el) => ber[el.dataset.key] = el.value);
      try { S.status = await api("berater_speichern", { berater: ber, datenschutz: $("ds").value }); $("berMsg").textContent = "✓ Gespeichert"; renderListe(); if (ersteinrichtung) zeigeEinstellungen(!einrichtungFertig(S.status)); }
      catch (e) { $("berMsg").textContent = e.message; }
    };
    $("bkGen").onclick = () => {
      const z = crypto.getRandomValues(new Uint8Array(30));
      const tok = btoa(String.fromCharCode(...z)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
      $("bkTok").type = "text"; $("bkTok").value = tok; $("bkGenText").textContent = tok; $("bkGenBox").hidden = false;
    };
    $("bkGenKop").onclick = (e) => kopieren($("bkGenText").textContent, e.target);
    $("bkVerb").onclick = async () => {
      const b2 = $("bkVerb"); b2.disabled = true; $("bkMsg").textContent = "Verbinde …";
      try {
        let tok = $("bkTok").value.trim();
        if (!tok && st.briefkasten.eingerichtet) { $("bkMsg").textContent = "Bitte den Zugangsschlüssel eingeben."; b2.disabled = false; return; }
        S.status = await api("briefkasten_verbinden", { adresse: $("bkAdr").value, zugang: tok });
        $("bkMsg").textContent = "✓ Verbunden. Ihr Schlüssel ist im Briefkasten hinterlegt.";
        aktualisieren(); if (ersteinrichtung) setTimeout(() => zeigeEinstellungen(!einrichtungFertig(S.status)), 800);
      } catch (e) { $("bkMsg").textContent = e.message; }
      b2.disabled = false;
    };
    const lesen = (f) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.onerror = rej; r.readAsDataURL(f); });
    $("vorlIn").onchange = async (e) => {
      const f = e.target.files[0]; e.target.value = ""; if (!f) return;
      $("vorlMsg").textContent = "Wird geprüft …";
      try { S.status = await api("vorlage_setzen", { inhalt: await lesen(f), name: f.name }); $("vorlMsg").textContent = `✓ ${S.status.vorlage.felder} Felder erkannt`; if (ersteinrichtung) setTimeout(() => zeigeEinstellungen(!einrichtungFertig(S.status)), 800); }
      catch (x) { $("vorlMsg").textContent = x.message; }
    };
    $("sichBtn").onclick = async () => {
      try { const p = await api("sicherung_erstellen", { passwort: $("sichPw").value }); $("sichMsg").innerHTML = `✓ Gespeichert: ${esc(p)}`; $("sichPw").value = ""; }
      catch (e) { $("sichMsg").textContent = e.message; }
    };
    $("wiedIn").onchange = async (e) => {
      const f = e.target.files[0]; e.target.value = ""; if (!f) return;
      if (!$("wiedPw").value) { $("wiedMsg").textContent = "Bitte zuerst das Passwort eingeben."; return; }
      $("wiedMsg").textContent = "Wird wiederhergestellt …";
      try { const n = await api("sicherung_laden", { inhalt: await lesen(f), passwort: $("wiedPw").value }); $("wiedMsg").textContent = `✓ ${n} Kunden wiederhergestellt`; aktualisieren(); }
      catch (x) { $("wiedMsg").textContent = x.message; }
    };
    $("updPruefen").onclick = async () => {
      $("updMsg").textContent = "Suche …";
      try {
        const u = await api("update_pruefen");
        $("updMsg").textContent = u.verfuegbar ? `Version ${u.neueste} ist verfügbar.` : `Sie haben die neueste Version (${u.aktuell}).`;
        $("updHinweise").textContent = u.verfuegbar ? u.hinweise : "";
        $("updInstall").hidden = !u.verfuegbar;
        if (u.verfuegbar && !u.installierbar) $("updMsg").textContent += " Einspielen geht nur in der installierten Notfallordner.exe.";
      } catch (e) { $("updMsg").textContent = e.message; }
    };
    $("updInstall").onclick = async () => {
      const b2 = $("updInstall"); b2.disabled = true; $("updPruefen").disabled = true;
      $("updMsg").textContent = "Update wird heruntergeladen und geprüft …";
      try {
        const r = await api("update_installieren");
        $("updMsg").textContent = `Version ${r.version} ist installiert. Das Programm startet jetzt neu …`;
      } catch (e) { $("updMsg").textContent = e.message; b2.disabled = false; $("updPruefen").disabled = false; }
    };
    $("ausgOeffnen").onclick = () => api("oeffnen", { pfad: st.ausgabe }).catch((e) => toast(e.message));
  }

  // ---------- Start ----------
  aktualisieren().then(() => { if (S.ansicht === "start") zeigeStart(); });
  setInterval(aktualisieren, 5000);
})();
