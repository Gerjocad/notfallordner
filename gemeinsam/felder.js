// Gemeinsame Felder und Prüfungen für Kundenformular (Briefkasten) und Windows-Programm.
// Stellt window.NFO bereit.
(function () {
  const VERWANDT = ["Ehepartner","Ehepartnerin","Lebenspartner","Lebenspartnerin","Vater","Mutter","Bruder","Schwester","Sohn","Tochter","Cousin","Cousine","Onkel","Tante","Ex-Mann","Ex-Frau","Freund","Freundin","Arbeitskollege","Arbeitskollegin","Nachbar","Nachbarin","Steuerberater","Steuerberaterin","Notar","Notarin","Rechtsanwalt","Rechtsanwältin","Vermögensverwalter","Vermögensverwalterin"];
  const POSITION = ["Repräsentant","Repräsentantin","Juniorberater","Juniorberaterin","Seniorberater","Seniorberaterin","Teamleiter","Teamleiterin","Repräsentanzleiter","Repräsentanzleiterin","Branch Manager","Branch Managerin","Regional Manager","Regional Managerin","Divisional Manager","Divisional Managerin","General Manager","General Managerin","Sales Consultant","Sales Consultantin","Senior Sales Consultant","Senior Sales Consultantin","Sales Manager","Sales Managerin","Senior Sales Manager","Senior Sales Managerin","General Sales Manager","General Sales Managerin"];

  // [Schlüssel, Beschriftung, Typ/Liste, Platzhalter]
  const F_KUNDE = [
    ["anrede", "Anrede", "list:dl-anrede", "Herr / Frau"], ["vorname", "Vorname (alle)", "", "Max Peter"], ["name", "Name", "", "Mustermann"],
    ["gebdat", "Geburtsdatum", "date"], ["gebort", "Geburtsort", "", "Köln"],
    ["strasse", "Straße, Hs.-Nr.", "", "Musterstraße 12"], ["plzort", "PLZ, Ort", "", "40212 Düsseldorf"],
    ["svnr", "SozialVersNr.", "", "12 150372 M 001"], ["steuerid", "Steuer-ID", "", "11 Ziffern"], ["perso", "PersonalausweisNr.", "", "9 Zeichen"], ["iban", "IBAN", "", "DE.."],
  ];
  const F_NF = [
    ["anrede", "Anrede", "list:dl-anrede", "Herr / Frau"], ["vorname", "Vorname", ""], ["name", "Name", ""],
    ["gebdat", "Geburtsdatum", "date"], ["strasse", "Straße, Hs.-Nr.", ""], ["plzort", "PLZ, Ort", "", "40212 Düsseldorf"],
    ["tel", "Telefon", ""], ["handy", "Handynummer", ""], ["mail", "Mailadresse", ""],
    ["verwandt", "Verwandtschaftsverhältnis", "list:dl-verwandt"], ["beruf", "Beruf", ""],
  ];
  const F_ARZT = [["praxis", "Name der Praxis", ""], ["strasse", "Straße, Hs.-Nr.", ""], ["plzort", "PLZ, Ort", ""], ["tel", "Telefon", ""]];
  const F_BERATER = [
    ["anrede", "Anrede", "list:dl-anrede", "Herr / Frau"], ["name", "Berater (Vor- und Nachname)", ""], ["position", "Position", "list:dl-position"],
    ["strasse", "Büro Straße, Hs.-Nr.", ""], ["plzort", "Büro PLZ, Ort", ""], ["mail", "Berater Mailadresse", ""],
    ["handy", "Berater Handynummer", ""], ["festnetz", "Berater FestnetzNr.", ""], ["fax", "Berater FaxNr.", ""],
    ["ausweis", "BeraterausweisNr.", ""], ["gebdat", "Berater Geburtsdatum", "date"], ["gebort", "Berater Geburtsort", ""],
  ];
  const REQUIRED = {
    kunde: ["anrede", "vorname", "name", "gebdat", "gebort", "strasse", "plzort"],
    "nf.0": ["vorname", "name", "plzort"],
    berater: ["anrede", "name", "strasse", "plzort", "mail", "handy"],
  };

  const t = (s) => String(s ?? "").trim();
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const isoToDate = (iso) => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || ""); return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null; };
  const heute = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), d.getDate()); };
  const digits = (s) => String(s).replace(/\D/g, "");
  const compact = (s) => String(s).replace(/[\s.-]/g, "").toUpperCase();

  function steuerIdOk(d) {
    let p = 10;
    for (let i = 0; i < 10; i++) { let s = (+d[i] + p) % 10; if (s === 0) s = 10; p = (s * 2) % 11; }
    return (11 - p) % 10 === +d[10];
  }
  function ibanOk(iban) {
    const r = iban.slice(4) + iban.slice(0, 4); let m = 0;
    for (const ch of r) { const v = /[A-Z]/.test(ch) ? String(ch.charCodeAt(0) - 55) : ch; for (const x of v) m = (m * 10 + +x) % 97; }
    return m === 1;
  }
  function svnrOk(s) {
    const n = s.slice(0, 8) + String(s.charCodeAt(8) - 64).padStart(2, "0") + s.slice(9, 11);
    const w = [2, 1, 2, 5, 7, 1, 2, 1, 2, 1, 2, 1]; let sum = 0;
    for (let i = 0; i < 12; i++) { const p = +n[i] * w[i]; sum += Math.floor(p / 10) + (p % 10); }
    return sum % 10 === +s[11];
  }
  const phoneRule = (v) => {
    if (/[^\d\s+/()-]/.test(v)) return { ok: false, msg: "Nur Ziffern, Leerzeichen und + / - ( ) erlaubt" };
    const n = digits(v).length;
    if (n < 6) return { ok: false, msg: `Mindestens 6 Ziffern – ${n} eingegeben` };
    if (n > 15) return { ok: false, msg: `Höchstens 15 Ziffern – ${n} eingegeben` };
    return { ok: true, msg: "" };
  };
  const RULES = {
    steuerid: (v) => {
      if (/[^\d\s]/.test(v)) return { ok: false, msg: "Nur Ziffern erlaubt" };
      const d = digits(v);
      if (d.length < 11) return { ok: false, msg: `11 Ziffern – ${d.length} eingegeben, noch ${11 - d.length}` };
      if (d.length > 11) return { ok: false, msg: `11 Ziffern – ${d.length} eingegeben, ${d.length - 11} zu viel` };
      if (d[0] === "0") return { ok: false, msg: "Die Steuer-ID beginnt nie mit 0" };
      if (!steuerIdOk(d)) return { ok: false, msg: "Prüfziffer stimmt nicht – bitte Zahlendreher prüfen" };
      return { ok: true, msg: "Steuer-ID gültig" };
    },
    iban: (v) => {
      const c = compact(v);
      if (/[^A-Z0-9]/.test(c)) return { ok: false, msg: "Nur Buchstaben und Ziffern erlaubt" };
      if (!/^[A-Z]{2}/.test(c)) return { ok: false, msg: "Beginnt mit dem Ländercode, z. B. DE" };
      const len = c.startsWith("DE") ? 22 : null;
      if (len && c.length !== len) return { ok: false, msg: `Deutsche IBAN: 22 Zeichen – ${c.length} eingegeben` + (c.length < 22 ? `, noch ${22 - c.length}` : `, ${c.length - 22} zu viel`) };
      if (!len && (c.length < 15 || c.length > 34)) return { ok: false, msg: `IBAN: 15 bis 34 Zeichen – ${c.length} eingegeben` };
      if (!ibanOk(c)) return { ok: false, msg: "Prüfziffer stimmt nicht – bitte Zahlendreher prüfen" };
      return { ok: true, msg: "IBAN gültig" };
    },
    svnr: (v, ctx) => {
      const c = compact(v);
      if (c.length < 12) return { ok: false, msg: `12 Zeichen – ${c.length} eingegeben, noch ${12 - c.length}` };
      if (c.length > 12) return { ok: false, msg: `12 Zeichen – ${c.length} eingegeben, ${c.length - 12} zu viel` };
      if (!/^\d{8}[A-Z]\d{3}$/.test(c)) return { ok: false, msg: "Aufbau: 8 Ziffern, 1 Buchstabe, 3 Ziffern" };
      if (!svnrOk(c)) return { ok: false, msg: "Prüfziffer stimmt nicht – bitte Zahlendreher prüfen" };
      const g = isoToDate(ctx && ctx.gebdat);
      if (g) {
        const ttmmjj = String(g.getDate()).padStart(2, "0") + String(g.getMonth() + 1).padStart(2, "0") + String(g.getFullYear()).slice(2);
        if (c.slice(2, 8) !== ttmmjj) return { ok: false, msg: `Ziffern 3–8 müssen das Geburtsdatum sein (${ttmmjj})` };
      }
      return { ok: true, msg: "Sozialversicherungsnummer gültig" };
    },
    perso: (v) => {
      const c = compact(v);
      if (/[^0-9CFGHJKLMNPRTVWXYZ]/.test(c)) return { ok: false, msg: "Ungültiges Zeichen (kein A, B, D, E, I, O, Q, S, U)" };
      if (c.length < 9) return { ok: false, msg: `9 Zeichen – ${c.length} eingegeben, noch ${9 - c.length}` };
      if (c.length > 10) return { ok: false, msg: `9 Zeichen – ${c.length} eingegeben, zu viele` };
      return { ok: true, msg: "" };
    },
    plzort: (v) => {
      const m = /^(\d*)\s*(.*)$/.exec(t(v));
      if (!m[1]) return { ok: false, msg: "Erst die 5-stellige PLZ, dann der Ort" };
      if (m[1].length !== 5) return { ok: false, msg: `PLZ hat 5 Ziffern – ${m[1].length} eingegeben` };
      if (!m[2]) return { ok: false, msg: "Nach der PLZ fehlt der Ort" };
      return { ok: true, msg: "" };
    },
    strasse: (v) => /[1-9]/.test(v) ? { ok: true, msg: "" } : { ok: false, msg: "Hausnummer fehlt (z. B. Musterstraße 12)" },
    mail: (v) => /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(t(v)) ? { ok: true, msg: "" } : { ok: false, msg: "E-Mail-Adresse unvollständig (z. B. name@beispiel.de)" },
    tel: phoneRule, handy: phoneRule, festnetz: phoneRule, fax: phoneRule,
    anrede: (v) => /^(Herr|Frau)$/.test(t(v)) ? { ok: true, msg: "" } : { ok: false, msg: "Bitte „Herr“ oder „Frau“" },
    name: (v) => /\d/.test(v) ? { ok: false, msg: "Namen enthalten keine Ziffern" } : { ok: true, msg: "" },
    vorname: (v) => /\d/.test(v) ? { ok: false, msg: "Namen enthalten keine Ziffern" } : { ok: true, msg: "" },
    gebdat: (v) => {
      const d = isoToDate(v); if (!d) return { ok: false, msg: "Datum unvollständig" };
      if (d > heute()) return { ok: false, msg: "Geburtsdatum liegt in der Zukunft" };
      if (heute().getFullYear() - d.getFullYear() > 115) return { ok: false, msg: "Geburtsdatum liegt zu weit zurück" };
      return { ok: true, msg: "" };
    },
  };

  const group = (path) => path.split(".")[0];
  const isRequired = (path, k) => (REQUIRED[path] || []).includes(k);
  function ruleFor(path, k) {
    if (group(path) === "termin") return null;
    if (path === "berater" && k === "gebdat") return null;
    return RULES[k] || null;
  }
  function checkValue(path, k, v, ctx) {
    if (!t(v)) return null;
    const r = ruleFor(path, k);
    return r ? r(v, ctx) : null;
  }
  function tidyValue(k, v) {
    let n = v;
    if (k === "iban") { const c = compact(v); if (/^[A-Z]{2}\d{2}[A-Z0-9]+$/.test(c)) n = c.replace(/(.{4})/g, "$1 ").trim(); }
    if (k === "steuerid") { const d = digits(v); if (d.length === 11 && !/[^\d\s]/.test(v)) n = `${d.slice(0, 2)} ${d.slice(2, 5)} ${d.slice(5, 8)} ${d.slice(8)}`; }
    if (k === "svnr") { const c = compact(v); if (/^\d{8}[A-Z]\d{3}$/.test(c)) n = `${c.slice(0, 2)} ${c.slice(2, 8)} ${c[8]} ${c.slice(9)}`; }
    if (k === "perso") n = compact(v);
    if (k === "anrede") { const a = t(v).toLowerCase(); if (a === "herr" || a === "frau") n = a[0].toUpperCase() + a.slice(1); }
    return n;
  }

  function fieldHtml(path, f, val) {
    const [k, label, type, ph] = f;
    const id = "in-" + path.replace(/\./g, "-") + "-" + k;
    const list = type && type.startsWith("list:") ? ` list="${type.slice(5)}"` : "";
    const ty = type === "date" ? "date" : "text";
    const req = isRequired(path, k) ? " *" : "";
    return `<div class="f"><label for="${id}">${esc(label)}${req}</label><input id="${id}" type="${ty}"${list} data-path="${path}" data-key="${k}" value="${esc(val)}"${ph ? ` placeholder="${esc(ph)}"` : ""} autocomplete="off" aria-describedby="${id}-msg"><small class="msg" id="${id}-msg" aria-live="polite"></small></div>`;
  }
  const fieldsHtml = (path, fields, obj) => `<div class="fields">${fields.map((f) => fieldHtml(path, f, (obj || {})[f[0]])).join("")}</div>`;
  const datalists = () =>
    `<datalist id="dl-anrede"><option value="Herr"><option value="Frau"></datalist>` +
    `<datalist id="dl-verwandt">${VERWANDT.map((v) => `<option value="${v}">`).join("")}</datalist>` +
    `<datalist id="dl-position">${POSITION.map((v) => `<option value="${v}">`).join("")}</datalist>`;

  // Feldzustand anzeigen. mark=true: Feld wurde verlassen -> Fehler rot
  function showCheck(el, mark, ctx) {
    const box = el.closest(".f"), msg = box && box.querySelector(".msg");
    if (!msg) return;
    const res = checkValue(el.dataset.path, el.dataset.key, el.value, ctx);
    const wasRed = box.classList.contains("invalid");
    if (!res) { box.classList.remove("invalid", "valid"); msg.textContent = ""; el.removeAttribute("aria-invalid"); return; }
    msg.textContent = res.msg;
    if (res.ok) { box.classList.remove("invalid"); box.classList.toggle("valid", !!res.msg); el.removeAttribute("aria-invalid"); }
    else { box.classList.remove("valid"); if (mark || wasRed) { box.classList.add("invalid"); el.setAttribute("aria-invalid", "true"); } }
  }

  // Alle Probleme eines Datensatzes
  function collectIssues(daten, berater, nurKontakte) {
    const out = [];
    const ctx = { gebdat: daten.kunde && daten.kunde.gebdat };
    const scan = (path, fields, obj, title, tab) => fields.forEach((f) => {
      const k = f[0], v = (obj || {})[k];
      const res = checkValue(path, k, v, ctx);
      if (res && !res.ok) out.push({ path, k, tab, text: `${title}: ${f[1]}`, why: res.msg, kind: "invalid" });
      else if (!t(v) && isRequired(path, k)) out.push({ path, k, tab, text: `${title}: ${f[1]}`, why: "fehlt", kind: "missing" });
    });
    if (!nurKontakte) scan("kunde", F_KUNDE, daten.kunde, "Kunde");
    (daten.nf || []).forEach((n, i) => { if (i === 0 || n.name || n.vorname) scan("nf." + i, F_NF, n, `${i + 1}. Kontakt`, i); });
    if (!nurKontakte) scan("arzt", F_ARZT, daten.arzt, "Hausarzt");
    if (berater) scan("berater", F_BERATER, berater, "Berater");
    return out;
  }

  window.NFO = { VERWANDT, POSITION, F_KUNDE, F_NF, F_ARZT, F_BERATER, REQUIRED, RULES, t, esc, isoToDate, heute,
    isRequired, checkValue, tidyValue, fieldHtml, fieldsHtml, datalists, showCheck, collectIssues };
})();
