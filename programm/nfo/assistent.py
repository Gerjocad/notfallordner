"""Kopier-Assistent: fragt die Stammdaten Feld für Feld ab. Der Berater kopiert im CRM (Strg+C),
das Programm übernimmt den Wert und springt zum nächsten Feld."""

from __future__ import annotations

import re

# Reihenfolge wie gewünscht: Formular-Reihenfolge, Ausweis vor SV-Nummer vor Steuer-ID vor IBAN
SCHRITTE = [
    ("anrede", "Anrede"),
    ("vorname", "Vorname"),
    ("name", "Name"),
    ("gebdat", "Geburtsdatum"),
    ("gebort", "Geburtsort"),
    ("strasse", "Straße und Hausnummer"),
    ("plzort", "PLZ und Ort"),
    ("perso", "Personalausweisnummer"),
    ("svnr", "Sozialversicherungsnummer"),
    ("steuerid", "Steuer-ID"),
    ("iban", "IBAN"),
]


def _einzeilig(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:200]


def datum(s: str) -> str | None:
    """„15.03.1972“, „15.3.72“, „1972-03-15“ -> „1972-03-15“."""
    s = s.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        j, mo, t = int(m[1]), int(m[2]), int(m[3])
    else:
        m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$", s)
        if not m:
            return None
        t, mo, j = int(m[1]), int(m[2]), int(m[3])
        if j < 100:
            j += 1900 if j > 30 else 2000
    if not (1 <= mo <= 12 and 1 <= t <= 31 and 1880 <= j <= 2100):
        return None
    return f"{j:04d}-{mo:02d}-{t:02d}"


def aufbereiten(feld: str, roh: str) -> tuple[str, dict]:
    """Kopierten Text für ein Feld aufbereiten. Gibt (Wert, weitere Felder) zurück."""
    weitere: dict = {}
    zeilen = [z.strip() for z in (roh or "").replace("\r", "").split("\n") if z.strip()]
    text = _einzeilig(roh)
    if feld == "anrede":
        a = text.lower().rstrip(".")
        text = "Herr" if a in ("herr", "hr", "mr") else "Frau" if a in ("frau", "fr", "mrs", "ms") else text
    elif feld == "gebdat":
        text = datum(text) or text
    elif feld == "strasse" and len(zeilen) >= 2 and re.match(r"^\d{5}\s+\S", zeilen[1]):
        # Straße und „PLZ Ort“ zusammen kopiert: beides übernehmen
        text, weitere["plzort"] = _einzeilig(zeilen[0]), _einzeilig(zeilen[1])
    elif feld == "perso":
        text = re.sub(r"[\s.-]", "", text).upper()
    elif feld == "svnr":
        c = re.sub(r"[\s.-]", "", text).upper()
        text = f"{c[:2]} {c[2:8]} {c[8]} {c[9:]}" if re.match(r"^\d{8}[A-Z]\d{3}$", c) else text
    elif feld == "steuerid":
        d = re.sub(r"\D", "", text)
        text = f"{d[:2]} {d[2:5]} {d[5:8]} {d[8:]}" if len(d) == 11 and not re.search(r"[^\d\s/.-]", text) else text
    elif feld == "iban":
        c = re.sub(r"[\s-]", "", text).upper()
        text = re.sub(r"(.{4})", r"\1 ", c).strip() if re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]+$", c) else text
    return text, weitere
