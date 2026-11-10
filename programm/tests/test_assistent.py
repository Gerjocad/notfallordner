"""Tests für den Kopier-Assistenten mit nachgestellter Zwischenablage."""

import time
from pathlib import Path

from nfo import assistent
from nfo.app import App, AppFehler
from nfo.speicher import Speicher


def test_aufbereiten():
    a = assistent.aufbereiten
    assert a("anrede", " Hr. ")[0] == "Herr" and a("anrede", "frau")[0] == "Frau"
    assert a("gebdat", "15.03.1972")[0] == "1972-03-15"
    assert a("gebdat", "5.3.72")[0] == "1972-03-05"
    assert a("gebdat", "1972-03-15")[0] == "1972-03-15"
    assert a("gebdat", "kein Datum")[0] == "kein Datum"
    assert a("strasse", "Musterstraße 12a\r\n50667 Köln") == ("Musterstraße 12a", {"plzort": "50667 Köln"})
    assert a("strasse", "Musterstraße  12a ")[0] == "Musterstraße 12a"
    assert a("perso", "l01x 00t47")[0] == "L01X00T47"
    assert a("svnr", "12150372m001")[0] == "12 150372 M 001"
    assert a("steuerid", "86095742719")[0] == "86 095 742 719"
    assert a("iban", "de02120300000000202051")[0] == "DE02 1203 0000 0000 2020 51"
    assert [s[0] for s in assistent.SCHRITTE][-4:] == ["perso", "svnr", "steuerid", "iban"]


class FakeAblage:
    ok = True

    def __init__(self):
        self.seq, self.inhalt = 1, ""

    def kopieren(self, text):
        self.inhalt, self.seq = text, self.seq + 1

    def sequenz(self):
        return self.seq

    def text(self):
        return self.inhalt


def _warte(bedingung, sek=3):
    ende = time.time() + sek
    while time.time() < ende:
        if bedingung():
            return True
        time.sleep(0.05)
    return False


def test_ablauf_mit_zwischenablage(tmp_path: Path):
    app = App(Speicher(tmp_path / "d"), tmp_path / "a")
    ablage = FakeAblage()
    ablage.kopieren("alter Inhalt vor dem Start")
    app.ablage = ablage
    k = app.kunde_neu("Max Mustermann", mit_link=False)
    s = app.assistent_start(k["id"])
    assert s["aktiv"] and s["schritt"] == 0 and not s["eigenes_fenster"]
    time.sleep(0.4)
    assert app.assistent_status()["schritt"] == 0  # alter Inhalt wird nicht übernommen

    def kopiere(text, schritt_danach):
        ablage.kopieren(text)
        assert _warte(lambda: app.assistent_status()["schritt"] == schritt_danach or app.assistent_status()["fertig"]), text

    kopiere("Herr", 1)
    kopiere("Max Peter", 2)
    # während der Assistent läuft, darf die Oberfläche nichts überschreiben
    try:
        app.kunde_speichern(k["id"], k["daten"])
        raise AssertionError("Speichern hätte blockiert werden müssen")
    except AppFehler as e:
        assert str(e) == "ASSISTENT_AKTIV"
    kopiere("Mustermann", 3)
    kopiere("15.03.1972", 4)
    kopiere("Köln", 5)
    kopiere("Musterstraße 12a\n50667 Köln", 7)  # PLZ/Ort gleich mit übernommen -> springt zur Ausweisnummer
    app.assistent_aktion("ueberspringen")  # Ausweisnummer liegt nicht vor
    assert app.assistent_status()["schritt"] == 8
    kopiere("12150372M001", 9)
    kopiere("86095742719", 10)
    ablage.kopieren("DE02120300000000202051")
    assert _warte(lambda: app.assistent_status()["fertig"])
    d = app.kunde(k["id"])["daten"]["kunde"]
    assert d == {"anrede": "Herr", "vorname": "Max Peter", "name": "Mustermann", "gebdat": "1972-03-15", "gebort": "Köln",
                 "strasse": "Musterstraße 12a", "plzort": "50667 Köln", "svnr": "12 150372 M 001",
                 "steuerid": "86 095 742 719", "perso": "", "iban": "DE02 1203 0000 0000 2020 51"}
    # nach dem Ende ist normales Speichern wieder möglich
    app.kunde_speichern(k["id"], app.kunde(k["id"])["daten"])


def test_zurueck_und_von_hand(tmp_path: Path):
    app = App(Speicher(tmp_path / "d"), tmp_path / "a")
    app.ablage = FakeAblage()
    app.ablage.ok = False  # wie im Browser: Werte werden eingefügt statt kopiert
    k = app.kunde_neu("Erika Muster", mit_link=False)
    app.assistent_start(k["id"])
    app.assistent_wert("Frau")
    app.assistent_wert("Erika")
    assert app.assistent_aktion("zurueck")["schritt"] == 1
    app.assistent_wert("Erika Maria")
    assert app.kunde(k["id"])["daten"]["kunde"]["vorname"] == "Erika Maria"
    s = app.assistent_aktion("beenden")
    assert s["fertig"] and not s["aktiv"]
