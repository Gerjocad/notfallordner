"""Tests für den Programmkern. Laufen unter Windows (in GitHub Actions) und Linux."""

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from nfo import krypto, merge, werte
from nfo.app import App, AppFehler
from nfo.speicher import Speicher

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _feld(instr: str, ergebnis: str = "«x»") -> str:
    return (f'<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> {instr} </w:instrText></w:r>'
            f'<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>{ergebnis}</w:t></w:r>'
            f'<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def _if_feld() -> str:
    # IF «NF1_TerminOrt» > " " "«NF1_TerminOrt», den «NF1_Termin»" ""
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> IF </w:instrText></w:r>'
            + _feld("MERGEFIELD NF1_TerminOrt") +
            '<w:r><w:instrText xml:space="preserve">&gt; " " "</w:instrText></w:r>'
            + _feld("MERGEFIELD NF1_TerminOrt") +
            '<w:r><w:instrText xml:space="preserve">, den </w:instrText></w:r>'
            + _feld("MERGEFIELD NF1_Termin") +
            '<w:r><w:instrText xml:space="preserve">" "" </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>alt</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>')


def vorlage() -> bytes:
    body = (f'<w:p>{_feld("MERGEFIELD Vorname")}<w:r><w:t xml:space="preserve"> </w:t></w:r>{_feld("MERGEFIELD Name")}</w:p>'
            f'<w:p>{_feld("MERGEFIELD M_1_Name")}</w:p>'
            f'<w:p>{_feld("MERGEFIELD Kunde_HausNr")}</w:p>'
            f'<w:p>{_if_feld()}</w:p>'
            f'<w:p>{_feld("FORMCHECKBOX", "")}</w:p>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body>{body}</w:body></w:document>')
        z.writestr("word/settings.xml", f'<w:settings {W}><w:mailMerge><w:query w:val="x"/></w:mailMerge></w:settings>')
    return buf.getvalue()


def _text(docx: bytes) -> list[str]:
    from lxml import etree
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(ns + "t")) for p in root.iter(ns + "p")]


def test_merge_felder_und_if():
    r = merge.fill_docx(vorlage(), {"Vorname": "Max", "Name": "Muster", "1. Name": "Erika", "Kunde Haus-Nr": "12a",
                                    "NF1 TerminOrt": "Köln", "NF1 Termin": "3. November 2026"})
    assert _text(r.data)[:4] == ["Max Muster", "Erika", "12a", "Köln, den 3. November 2026"]
    assert r.skipped == 0 and r.missing == []
    assert b"mailMerge" not in zipfile.ZipFile(io.BytesIO(r.data)).read("word/settings.xml")
    assert b"FORMCHECKBOX" in zipfile.ZipFile(io.BytesIO(r.data)).read("word/document.xml")
    assert b"<w:b/>" in zipfile.ZipFile(io.BytesIO(r.data)).read("word/document.xml")  # Formatierung bleibt


def test_merge_if_leer():
    r = merge.fill_docx(vorlage(), {"NF1 TerminOrt": "", "NF1 Termin": "3. November 2026"})
    assert _text(r.data)[3] == ""
    assert "Vorname" in r.missing


def test_werte():
    assert werte.strasse_nr("Musterstraße 12a") == ("Musterstraße", "12a")
    assert werte.strasse_nr("Straße des 17. Juni 4") == ("Straße des", "17. Juni 4")  # wie die Excel
    assert werte.plz_ort("40212 Düsseldorf") == ("40212", "Düsseldorf")
    assert [d.isoformat() for d in werte.jahrestage("2026-11-03")][:2] == ["2031-12-01", "2036-12-01"]
    assert werte.jahrestage("2026-12-10")[0] == date(2032, 1, 1)
    k = werte.leer_kunde()
    k["kunde"].update(vorname="Max", name="Muster", strasse="Weg 3", plzort="50667 Köln", gebdat="1972-03-15")
    b = {"plzort": "40212 Düsseldorf", "name": "Anna"}
    o = werte.befuellung(k, b, date(2026, 11, 6))
    assert o["Kunde Haus-Nr"] == "3" and o["Kunde Ort"] == "Köln" and o["Geburtsdatum"] == "15.03.1972"
    assert o["NFO TerminOrt"] == "Düsseldorf" and o["NFO Termin"] == "6. November 2026"
    assert o["NF1 TerminOrt"] == ""


def test_bereinigen_entfernt_fremdes():
    d = werte.bereinigen({"kunde": {"name": "  X  ", "boese": "1"}, "nf": [{"name": "A" * 500}], "extra": 1})
    assert d["kunde"]["name"] == "X" and "boese" not in d["kunde"] and "extra" not in d
    assert len(d["nf"]) == 3 and len(d["nf"][0]["name"]) == 200


def test_krypto_umschlag():
    priv, pub = krypto.neues_schluesselpaar()
    u = krypto.verschliessen_fuer_test(pub, {"kunde": {"name": "Müller"}})
    assert krypto.oeffnen(priv, u)["kunde"]["name"] == "Müller"
    priv2, _ = krypto.neues_schluesselpaar()
    with pytest.raises(Exception):
        krypto.oeffnen(priv2, u)


def test_schuetzen_und_sicherung():
    assert krypto.entschuetzen(krypto.schuetzen(b"geheim")) == b"geheim"
    s = krypto.mit_passwort(b"daten", "passwort123")
    assert krypto.ohne_passwort(s, "passwort123") == b"daten"
    with pytest.raises(Exception):
        krypto.ohne_passwort(s, "falsch")


class FakeBriefkasten:
    """Ersetzt den Online-Briefkasten im Test."""

    def __init__(self):
        self.pub, self.einladungen, self.eingang, self.adresse, self.zugang = None, set(), [], "https://test", "x" * 30

    def pruefen(self):
        return {"ok": True}

    def schluessel_hinterlegen(self, pub, kid, berater=None):
        self.pub = pub

    def einladung_anlegen(self):
        eid = f"einladung{len(self.einladungen):08d}"
        self.einladungen.add(eid)
        return eid, self.link(eid)

    def einladung_loeschen(self, eid):
        self.einladungen.discard(eid)

    def link(self, eid):
        return f"{self.adresse}/f/{eid}"

    def posteingang(self, voll=False):
        return list(self.eingang)

    def abgeholt(self, eid):
        self.eingang = [i for i in self.eingang if i["id"] != eid]


def test_ablauf(tmp_path: Path, monkeypatch):
    import base64
    bk = FakeBriefkasten()
    app = App(Speicher(tmp_path / "daten"), tmp_path / "ausgabe")
    monkeypatch.setattr(app, "_bk", lambda: bk)
    monkeypatch.setattr("nfo.app.Briefkasten", lambda a, z: bk)
    app.berater_speichern({"name": "Anna Beispiel", "plzort": "40212 Düsseldorf"})
    app.briefkasten_verbinden("https://test", "x" * 30)
    k = app.kunde_neu("Max Mustermann")
    assert k["status"] == "eingeladen" and "Hallo Max" in k["nachricht"] and k["link"]
    eid = next(iter(bk.einladungen))
    # Berater trägt die Kundendaten selbst ein
    d = app.kunde(k["id"])["daten"]
    d["kunde"]["iban"] = "DE02"
    d["arzt"]["praxis"] = "Dr. X"
    app.kunde_speichern(k["id"], d)
    # Kunde schickt nur die Notfallkontakte (auch wenn jemand mehr mitschickt, wird nur nf übernommen)
    u = krypto.verschliessen_fuer_test(base64.b64decode(bk.pub), {"nf": [{"vorname": "Erika"}], "kunde": {"iban": "FREMD"}})
    bk.eingang.append({"id": eid, "received": 1_700_000_000_000, "envelope": u})
    assert app.abrufen()["neu"] == 1 and bk.eingang == []
    k2 = app.kunde(k["id"])
    assert k2["status"] == "eingegangen" and k2["neu"]
    assert k2["daten"]["kunde"]["iban"] == "DE02" and k2["daten"]["arzt"]["praxis"] == "Dr. X"
    assert k2["daten"]["nf"][0]["vorname"] == "Erika" and k2["daten"]["kunde"]["name"] == "Mustermann"
    assert "Notfallkontakte" in k["nachricht"]
    # alter Stand darf neue Daten nicht überschreiben
    with pytest.raises(AppFehler):
        app.kunde_speichern(k["id"], k["daten"], stand=None)
    app.kunde_speichern(k["id"], k2["daten"], stand=k2["eingang"])
    with pytest.raises(AppFehler):
        app.ordner_erstellen(k["id"])  # noch keine Vorlage
    app.vorlage_setzen(vorlage(), "vorlage.docx")
    erg = app.ordner_erstellen(k["id"], mit_pdf=False)
    assert Path(erg["word"]).exists() and "Mustermann, Max" in erg["ordner"]
    assert app.kunden()[0]["status"] == "erstellt"
    # Sicherung und Wiederherstellung in neuem Speicher
    datei = Path(app.sicherung_erstellen("passwort123"))
    app2 = App(Speicher(tmp_path / "neu"), tmp_path / "ausgabe2")
    assert app2.sicherung_laden(datei.read_bytes(), "passwort123") == 1
    assert app2.kunden()[0]["name"] == "Max Mustermann" and app2.vorlage_pfad().exists()
    with pytest.raises(AppFehler):
        app2.sicherung_laden(datei.read_bytes(), "falsch123")


def test_update_pruefen(tmp_path, monkeypatch):
    import hashlib, json
    from nfo import update
    neu = b"neue exe"
    info = {"version": "99.0.0", "url": "https://x/neu.exe", "sha256": hashlib.sha256(neu).hexdigest(), "hinweise": "Neu"}
    monkeypatch.setattr(update, "_laden", lambda url, timeout=30: json.dumps(info).encode() if url.endswith(".json") else neu)
    r = update.pruefen("https://x/update.json")
    assert r["verfuegbar"] and r["neueste"] == "99.0.0"
    # Austausch einer "laufenden" exe nachstellen
    exe = tmp_path / "Notfallordner.exe"
    exe.write_bytes(b"alte exe")
    assert update.herunterladen_und_tauschen(r, exe) == exe.resolve()
    assert exe.read_bytes() == neu and (tmp_path / "Notfallordner.alt.exe").read_bytes() == b"alte exe"
    # beschädigter Download wird abgelehnt, nichts wird ersetzt
    r["sha256"] = "0" * 64
    with pytest.raises(update.UpdateFehler):
        update.herunterladen_und_tauschen(r, exe)
    assert exe.read_bytes() == neu
    assert update._version("1.10.0") > update._version("1.9.3")
    info["version"] = "0.1"
    assert not update.pruefen("https://x/update.json")["verfuegbar"]
