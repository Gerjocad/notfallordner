"""Werte für die Word-Vorlage berechnen, wie im Excel-Blatt „Befüllung“."""

from __future__ import annotations

import re
from datetime import date

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]

KUNDE_FELDER = ["anrede", "vorname", "name", "gebdat", "gebort", "strasse", "plzort", "svnr", "steuerid", "perso", "iban"]
NF_FELDER = ["anrede", "vorname", "name", "gebdat", "strasse", "plzort", "tel", "handy", "mail", "verwandt", "beruf"]
ARZT_FELDER = ["praxis", "strasse", "plzort", "tel"]
BERATER_FELDER = ["anrede", "name", "position", "strasse", "plzort", "mail", "handy", "festnetz", "fax", "ausweis", "gebdat", "gebort"]


def leer_kunde() -> dict:
    return {
        "kunde": {k: "" for k in KUNDE_FELDER},
        "nf": [{k: "" for k in NF_FELDER} for _ in range(3)],
        "arzt": {k: "" for k in ARZT_FELDER},
        "termin": {"kunde": {"datum": "", "ort": ""}, "nf": [{"datum": "", "ort": ""} for _ in range(3)]},
    }


def bereinigen(daten: dict) -> dict:
    """Unbekannte Schlüssel entfernen, fehlende ergänzen, alles zu kurzen Strings machen."""
    out = leer_kunde()
    s = lambda v: str(v or "").strip()[:200]  # noqa: E731
    for k in KUNDE_FELDER:
        out["kunde"][k] = s((daten.get("kunde") or {}).get(k))
    for i in range(3):
        src = ((daten.get("nf") or []) + [{}, {}, {}])[i] or {}
        for k in NF_FELDER:
            out["nf"][i][k] = s(src.get(k))
    for k in ARZT_FELDER:
        out["arzt"][k] = s((daten.get("arzt") or {}).get(k))
    t = daten.get("termin") or {}
    out["termin"]["kunde"] = {k: s((t.get("kunde") or {}).get(k)) for k in ("datum", "ort")}
    for i in range(3):
        src = ((t.get("nf") or []) + [{}, {}, {}])[i] or {}
        out["termin"]["nf"][i] = {k: s(src.get(k)) for k in ("datum", "ort")}
    return out


def iso(s: str) -> date | None:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s or "")
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def ttmmjjjj(s: str) -> str:
    d = iso(s)
    return d.strftime("%d.%m.%Y") if d else ""


def lang(d: date | None) -> str:
    return f"{d.day}. {MONATE[d.month - 1]} {d.year}" if d else ""


def strasse_nr(s: str) -> tuple[str, str]:
    """„Musterstraße 12a“ -> („Musterstraße“, „12a“): Trennung an der ersten Ziffer 1–9 (wie die Excel)."""
    s = (s or "").strip()
    m = re.search(r"[1-9]", s)
    if m and m.start() > 0:
        return s[: m.start()].strip(), s[m.start():].strip()
    return s, ""


def plz_ort(s: str) -> tuple[str, str]:
    s = (s or "").strip()
    m = re.match(r"^(\d{4,5})\s+(.*)$", s)
    return (m[1], m[2].strip()) if m else ("", s)


def jahrestage(termin: str, heute: date | None = None) -> list[date]:
    """7 Termine zur Erneuerung der Patientenverfügung: alle 5 Jahre, jeweils am 1. des Folgemonats."""
    d = iso(termin) or heute or date.today()
    y, m = d.year + 5, d.month + 1
    if m > 12:
        m, y = 1, y + 1
    return [date(y + i * 5, m, 1) for i in range(7)]


def befuellung(kunde: dict, berater: dict, heute: date | None = None) -> dict[str, str]:
    """Spaltennamen des Blatts „Befüllung“ -> Text."""
    heute = heute or date.today()
    k, a, b = kunde["kunde"], kunde["arzt"], berater
    o = {
        "Name": k["name"], "Vorname": k["vorname"], "Geburtsdatum": ttmmjjjj(k["gebdat"]), "Geburtsort": k["gebort"],
        "Straße": k["strasse"], "Ort": k["plzort"], "SozialVersNr": k["svnr"], "Steuer ID": k["steuerid"],
        "PersonalausweisNr": k["perso"], "IBAN": k["iban"],
        "tecis Berater Herr/Frau": b.get("anrede", ""), "tecis Berater": b.get("name", ""),
        "Büro Straße": b.get("strasse", ""), "Büro Ort": b.get("plzort", ""),
        "Berater Mailadresse": b.get("mail", ""), "Berater Handynummer": b.get("handy", ""),
        "Berater FestnetzNr": b.get("festnetz", ""), "Berater FaxNr": b.get("fax", ""),
        "BeraterausweisNr": b.get("ausweis", ""), "Berater Gebrutsdatum": ttmmjjjj(b.get("gebdat", "")),
        "Berater Geburtsort": b.get("gebort", ""),
    }
    for i, n in enumerate(kunde["nf"]):
        p = f"{i + 1}. "
        o.update({
            p + "Name": n["name"], p + "Vorname": n["vorname"], p + "Geburtsdatum": ttmmjjjj(n["gebdat"]),
            p + "Straße, Nr.": n["strasse"], p + "PLZ Ort": n["plzort"], p + "Telefon": n["tel"],
            p + "HandyNr": n["handy"], p + "E-Mailadresse": n["mail"] if "@" in n["mail"] else "",
        })
    o.update({"Name der Praxis": a["praxis"], "Arzt Straße, Hs.-Nr.": a["strasse"],
              "Arzt PLZ, Ort": a["plzort"], "Arzt Telefon": a["tel"]})
    ks, kp = strasse_nr(k["strasse"]), plz_ort(k["plzort"])
    o.update({"Kunde Anrede": k["anrede"], "Kunde Straße": ks[0], "Kunde Haus-Nr": ks[1],
              "Kunde PLZ": kp[0], "Kunde Ort": kp[1]})
    for i, n in enumerate(kunde["nf"]):
        s, p, q = strasse_nr(n["strasse"]), plz_ort(n["plzort"]), f"NF{i + 1} "
        o.update({q + "Anrede": n["anrede"], q + "Straße": s[0], q + "Haus-Nr": s[1], q + "PLZ": p[0], q + "Ort": p[1]})
    for i, t in enumerate(kunde["termin"]["nf"]):
        o[f"NF{i + 1} Termin"] = lang(iso(t["datum"]) or heute)
        o[f"NF{i + 1} TerminOrt"] = t["ort"] or plz_ort(kunde["nf"][i]["plzort"])[1]
    tk = kunde["termin"]["kunde"]
    o["NFO Termin"] = lang(iso(tk["datum"]) or heute)
    o["NFO TerminOrt"] = tk["ort"] or plz_ort(b.get("plzort", ""))[1]
    for i, d in enumerate(jahrestage(tk["datum"], heute)):
        o[f"Jahrestag NFO {i + 1}"] = lang(d)
    o["Berater Position"] = b.get("position", "")
    return o


def anzeige_name(kunde: dict) -> str:
    k = kunde["kunde"]
    return " ".join(x for x in (k["vorname"].split(" ")[0] if k["vorname"] else "", k["name"]) if x).strip()
