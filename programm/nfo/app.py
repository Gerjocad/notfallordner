"""Programmlogik: Kunden, Briefkasten-Abruf, Notfallordner erstellen, Sicherung."""

from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

from . import __version__, krypto, merge, pdf, update, werte
from . import assistent as kopier
from .zwischenablage import Zwischenablage
from .briefkasten import Briefkasten, BriefkastenFehler
from .speicher import Speicher, dokumente_ordner

ABRUF_SEKUNDEN = 60
LINK_GUELTIG_TAGE = 60


class AppFehler(Exception):
    pass


def _dateiname(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s or "").strip(" .")
    return re.sub(r"\s+", " ", s) or "Kunde"


class App:
    def __init__(self, speicher: Speicher | None = None, ausgabe: Path | None = None):
        self.sp = speicher or Speicher()
        self.ausgabe = Path(ausgabe or dokumente_ordner())
        self.lock = threading.Lock()
        self.abruf = {"zeit": None, "fehler": None, "laeuft": False}
        self._stop = threading.Event()
        self.update_info: dict | None = None
        self.neustart = None  # wird von __main__ gesetzt: startet die neue .exe und beendet dieses Programm
        # Kopier-Assistent
        self.ass: dict | None = None
        self.ass_lock = threading.RLock()
        self.ablage = Zwischenablage()
        self.assistent_fenster = None  # von __main__ gesetzt: öffnet das kleine Fenster, gibt True zurück
        self.assistent_fenster_zu = None

    # ---------- Einstellungen ----------
    def _bk(self) -> Briefkasten | None:
        e = self.sp.hole("briefkasten")
        return Briefkasten(e["adresse"], e["zugang"]) if e and e.get("adresse") and e.get("zugang") else None

    def berater(self) -> dict:
        b = self.sp.hole("berater") or {}
        return {k: str(b.get(k, "") or "") for k in werte.BERATER_FELDER}

    def vorlage_pfad(self) -> Path:
        return self.sp.ordner / "vorlage.docx"

    def status(self) -> dict:
        e = self.sp.hole("briefkasten") or {}
        v = self.vorlage_pfad()
        vorlage = None
        if v.exists():
            vorlage = {"name": self.sp.hole("vorlage_name", "vorlage.docx"), "felder": merge.count_fields(v.read_bytes()),
                       "groesse": v.stat().st_size}
        kunden = self.sp.kunden()
        return {
            "briefkasten": {"adresse": e.get("adresse", ""), "eingerichtet": bool(e.get("adresse") and e.get("zugang")),
                            "letzter_abruf": self.abruf["zeit"], "fehler": self.abruf["fehler"]},
            "vorlage": vorlage,
            "berater": self.berater(),
            "pdf": pdf.verfuegbar(),
            "neu": sum(1 for k in kunden if k["neu"]),
            "ausgabe": str(self.ausgabe),
            "datenschutz": self.sp.hole("datenschutz", ""),
            "version": __version__,
            "update": self.update_info,
        }

    def berater_speichern(self, berater: dict, datenschutz: str | None = None) -> dict:
        b = {k: str((berater or {}).get(k, "") or "").strip()[:200] for k in werte.BERATER_FELDER}
        self.sp.setze("berater", b)
        if datenschutz is not None:
            self.sp.setze("datenschutz", str(datenschutz).strip()[:2000])
        bk = self._bk()
        if bk:  # Name des Beraters im Kundenformular aktuell halten
            try:
                self._schluessel_hochladen(bk)
            except BriefkastenFehler:
                pass
        return self.status()

    def _schluessel_hochladen(self, bk: Briefkasten) -> None:
        pub = self.sp.hole("schluessel_pub")
        if not pub:
            priv, pub_der = krypto.neues_schluesselpaar()
            self.sp.setze("schluessel_priv", priv.decode())
            pub = base64.b64encode(pub_der).decode()
            self.sp.setze("schluessel_pub", pub)
        b = self.berater()
        bk.schluessel_hinterlegen(pub, krypto.fingerabdruck(base64.b64decode(pub)),
                                  {"name": b["name"], "mail": b["mail"], "tel": b["handy"], "datenschutz": self.sp.hole("datenschutz", "")})

    def briefkasten_verbinden(self, adresse: str, zugang: str) -> dict:
        bk = Briefkasten(adresse, zugang)
        bk.pruefen()  # wirft BriefkastenFehler mit verständlicher Meldung
        self._schluessel_hochladen(bk)
        self.sp.setze("briefkasten", {"adresse": bk.adresse, "zugang": bk.zugang})
        self.abruf["fehler"] = None
        return self.status()

    def vorlage_setzen(self, inhalt: bytes, name: str) -> dict:
        n = merge.count_fields(inhalt)
        if n < 0:
            raise AppFehler("Das ist keine gültige Word-Datei (.docx)")
        if n == 0:
            raise AppFehler("In dieser Datei sind keine Serienbrieffelder. Bitte die Notfallordner-Vorlage wählen.")
        self.vorlage_pfad().write_bytes(inhalt)
        self.sp.setze("vorlage_name", os.path.basename(name or "vorlage.docx"))
        return self.status()

    # ---------- Kunden ----------
    def _uebersicht(self, k: dict) -> dict:
        d = k["daten"]
        name = werte.anzeige_name(d) or d.get("bezeichnung") or "Ohne Namen"
        heute = date.today()
        hinweis = None
        if k["status"] == "eingeladen" and k["erstellt"] and (time.time() - k["erstellt"]) > LINK_GUELTIG_TAGE * 86400:
            hinweis = "Link abgelaufen"
        faellig = None
        if k["ordner_erstellt"]:
            # Erneuerung anzeigen: ab 60 Tage vorher bis 1 Jahr danach
            for j in werte.jahrestage(d["termin"]["kunde"]["datum"], date.fromtimestamp(k["ordner_erstellt"])):
                if -365 <= (j - heute).days <= 60:
                    faellig = j.isoformat()
                    break
        return {"id": k["id"], "name": name, "status": k["status"], "neu": k["neu"], "erstellt": k["erstellt"],
                "geaendert": k["geaendert"], "eingang": k["eingang"], "ordner_erstellt": k["ordner_erstellt"],
                "termin": d["termin"]["kunde"]["datum"], "hinweis": hinweis, "erneuerung": faellig,
                "bezeichnung": d.get("bezeichnung", "")}

    def kunden(self) -> list[dict]:
        return [self._uebersicht(k) for k in self.sp.kunden()]

    def kunde(self, kid: str) -> dict:
        k = self.sp.kunde(kid)
        if not k:
            raise AppFehler("Kunde nicht gefunden")
        bk = self._bk()
        out = self._uebersicht(k)
        out["daten"] = k["daten"]
        out["link"] = bk.link(k["einladung"]) if bk and k["einladung"] and k["status"] == "eingeladen" else None
        out["jahrestage"] = [d.isoformat() for d in werte.jahrestage(k["daten"]["termin"]["kunde"]["datum"])]
        out["ordner"] = str(self._kundenordner(k["daten"])) if k["ordner_erstellt"] else None
        return out

    def _nachricht(self, vorname: str, link: str) -> str:
        b = self.berater()
        gruss = f"Hallo {vorname}," if vorname else "Hallo,"
        return (f"{gruss}\n\nfür Ihren Notfallordner fehlen mir nur noch Ihre Notfallkontakte. "
                f"Bitte tragen Sie diese über Ihren persönlichen Link ein:\n"
                f"{link}\n\nDie Angaben werden verschlüsselt übertragen und nur bei mir gespeichert. "
                f"Der Link kann nur einmal verwendet werden.\n\nViele Grüße\n{b['name']}").strip()

    def kunde_neu(self, bezeichnung: str, mit_link: bool = True) -> dict:
        bezeichnung = str(bezeichnung or "").strip()[:120]
        daten = werte.leer_kunde()
        daten["bezeichnung"] = bezeichnung
        teile = bezeichnung.split()
        if len(teile) >= 2:
            daten["kunde"]["vorname"], daten["kunde"]["name"] = " ".join(teile[:-1]), teile[-1]
        elif teile:
            daten["kunde"]["name"] = teile[0]
        if mit_link:
            bk = self._bk()
            if not bk:
                raise AppFehler("Bitte zuerst den Briefkasten einrichten (Einstellungen)")
            eid, link = bk.einladung_anlegen()
            k = self.sp.neuer_kunde(daten, "eingeladen", eid)
            out = self.kunde(k["id"])
            out["nachricht"] = self._nachricht(teile[0] if len(teile) >= 2 else "", link)
            return out
        k = self.sp.neuer_kunde(daten, "manuell")
        return self.kunde(k["id"])

    def link_neu(self, kid: str) -> dict:
        k = self.sp.kunde(kid)
        if not k:
            raise AppFehler("Kunde nicht gefunden")
        bk = self._bk()
        if not bk:
            raise AppFehler("Bitte zuerst den Briefkasten einrichten (Einstellungen)")
        if k["einladung"]:
            try:
                bk.einladung_loeschen(k["einladung"])
            except BriefkastenFehler:
                pass
        eid, link = bk.einladung_anlegen()
        self.sp.aktualisiere(kid, einladung=eid, status="eingeladen")
        self.sp.db.execute("UPDATE kunden SET erstellt=? WHERE id=?", (time.time(), kid))
        self.sp.db.commit()
        out = self.kunde(kid)
        vorname = k["daten"]["kunde"]["vorname"].split(" ")[0] if k["daten"]["kunde"]["vorname"] else ""
        out["nachricht"] = self._nachricht(vorname, link)
        return out

    def kunde_speichern(self, kid: str, daten: dict, stand: float | None = None) -> dict:
        k = self.sp.kunde(kid)
        if not k:
            raise AppFehler("Kunde nicht gefunden")
        if self.ass and self.ass["kid"] == kid and not self.ass["fertig"]:
            raise AppFehler("ASSISTENT_AKTIV")  # der Kopier-Assistent schreibt gerade in diesen Kunden
        if (k["eingang"] or None) != (stand or None):
            # Inzwischen sind Daten vom Kunden eingegangen: nicht mit dem alten Stand überschreiben
            raise AppFehler("NEUE_DATEN")
        neu = werte.bereinigen(daten)
        neu["bezeichnung"] = k["daten"].get("bezeichnung", "")
        self.sp.aktualisiere(kid, daten=neu)
        return self._uebersicht(self.sp.kunde(kid))

    def gelesen(self, kid: str) -> None:
        self.sp.aktualisiere(kid, neu=False)

    def kunde_loeschen(self, kid: str) -> None:
        k = self.sp.kunde(kid)
        if k and k["einladung"] and k["status"] == "eingeladen":
            bk = self._bk()
            if bk:
                try:
                    bk.einladung_loeschen(k["einladung"])
                except BriefkastenFehler:
                    pass
        self.sp.loesche(kid)

    # ---------- Briefkasten abrufen ----------
    def abrufen(self) -> dict:
        """Neue Einsendungen holen, entschlüsseln, speichern und im Briefkasten löschen."""
        bk = self._bk()
        if not bk:
            return {"neu": 0}
        with self.lock:
            self.abruf["laeuft"] = True
            neu = 0
            try:
                priv = (self.sp.hole("schluessel_priv") or "").encode()
                self._abrufe = getattr(self, "_abrufe", 0) + 1
                for item in bk.posteingang(voll=self._abrufe % 30 == 1):
                    eid = item.get("id", "")
                    try:
                        inhalt = krypto.oeffnen(priv, item["envelope"])
                    except Exception:  # noqa: BLE001 - mit anderem Schlüssel verschlüsselt o. ä.
                        continue
                    k = self.sp.kunde_per_einladung(eid)
                    if k:
                        daten = k["daten"]
                    else:
                        daten = werte.leer_kunde()
                        daten["bezeichnung"] = "Eingang ohne Einladung"
                    # Der Kunde liefert nur die Notfallkontakte, alles andere trägt der Berater ein
                    eingang = werte.bereinigen({**daten, "nf": inhalt.get("nf")})
                    eingang["termin"] = werte.bereinigen(daten)["termin"]
                    eingang["bezeichnung"] = daten.get("bezeichnung", "")
                    zeit = (item.get("received") or time.time() * 1000) / 1000
                    if k:
                        self.sp.aktualisiere(k["id"], daten=eingang, status="eingegangen", eingang=zeit, neu=True)
                    else:
                        nk = self.sp.neuer_kunde(eingang, "eingegangen", eid)
                        self.sp.aktualisiere(nk["id"], eingang=zeit, neu=True)
                    bk.abgeholt(eid)  # erst nach dem sicheren Speichern löschen
                    neu += 1
                self.abruf["fehler"] = None
            except BriefkastenFehler as e:
                self.abruf["fehler"] = str(e)
            finally:
                self.abruf["zeit"] = time.time()
                self.abruf["laeuft"] = False
        return {"neu": neu, "fehler": self.abruf["fehler"]}

    def starte_abruf(self) -> None:
        def schleife():
            while not self._stop.is_set():
                try:
                    self.abrufen()
                except Exception as e:  # noqa: BLE001
                    self.abruf["fehler"] = f"Abruf fehlgeschlagen: {e}"
                self._stop.wait(ABRUF_SEKUNDEN)
        threading.Thread(target=schleife, daemon=True, name="briefkasten").start()

    def stop(self) -> None:
        self._stop.set()

    # ---------- Notfallordner erstellen ----------
    def _kundenordner(self, daten: dict) -> Path:
        k = daten["kunde"]
        name = _dateiname(f"{k['name']}, {k['vorname']}" if k["name"] and k["vorname"] else (werte.anzeige_name(daten) or daten.get("bezeichnung") or "Kunde"))
        return self.ausgabe / name

    def ordner_erstellen(self, kid: str, mit_pdf: bool = True) -> dict:
        k = self.sp.kunde(kid)
        if not k:
            raise AppFehler("Kunde nicht gefunden")
        if not self.vorlage_pfad().exists():
            raise AppFehler("Bitte zuerst die Word-Vorlage wählen (Einstellungen)")
        daten = werte.bereinigen(k["daten"])
        werte_ = werte.befuellung(daten, self.berater())
        r = merge.fill_docx(self.vorlage_pfad().read_bytes(), werte_)
        ordner = self._kundenordner(daten)
        ordner.mkdir(parents=True, exist_ok=True)
        kurz = _dateiname(f"{daten['kunde']['vorname'].split(' ')[0]} {daten['kunde']['name']}".strip()) if daten["kunde"]["name"] else "Kunde"
        stempel = datetime.now().strftime("%Y-%m-%d")
        docx = ordner / f"02_Notfallordner_2.5_{kurz}_{stempel}.docx"
        docx.write_bytes(r.data)
        ergebnis = {"ordner": str(ordner), "word": str(docx), "pdf": None, "pdf_mit": None, "pdf_fehler": None,
                    "felder": r.done, "unbekannt": r.missing, "uebersprungen": r.skipped}
        if mit_pdf:
            ziel = docx.with_suffix(".pdf")
            try:
                ergebnis["pdf_mit"] = pdf.word_zu_pdf(docx, ziel)
                ergebnis["pdf"] = str(ziel)
            except pdf.PdfFehler as e:
                ergebnis["pdf_fehler"] = str(e)
            except Exception as e:  # noqa: BLE001
                ergebnis["pdf_fehler"] = f"PDF konnte nicht erstellt werden: {e}"
        self.sp.aktualisiere(kid, status="erstellt", ordner_erstellt=time.time(), neu=False)
        return ergebnis

    def oeffnen(self, pfad: str) -> None:
        p = Path(pfad)
        if p == self.ausgabe:
            p.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            raise AppFehler("Datei oder Ordner nicht gefunden")
        if sys.platform == "win32":
            os.startfile(str(p))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])

    # ---------- Kopier-Assistent ----------
    def assistent_start(self, kid: str) -> dict:
        if not self.sp.kunde(kid):
            raise AppFehler("Kunde nicht gefunden")
        with self.ass_lock:
            self.ass = {"kid": kid, "schritt": 0, "seq": self.ablage.sequenz(), "fertig": False, "version": 0,
                        "erledigt": set()}
        if self.ablage.ok:
            threading.Thread(target=self._assistent_beobachten, daemon=True, name="zwischenablage").start()
        fenster = bool(self.assistent_fenster and self.assistent_fenster())
        out = self.assistent_status()
        out["eigenes_fenster"] = fenster
        return out

    def assistent_status(self) -> dict:
        a = self.ass
        if not a:
            return {"aktiv": False, "fertig": True}
        k = self.sp.kunde(a["kid"])
        if not k:
            return {"aktiv": False, "fertig": True}
        werte_ = k["daten"]["kunde"]
        return {
            "aktiv": not a["fertig"], "fertig": a["fertig"], "kid": a["kid"], "version": a["version"],
            "schritt": a["schritt"], "gesamt": len(kopier.SCHRITTE), "zwischenablage": self.ablage.ok,
            "name": werte.anzeige_name(k["daten"]) or k["daten"].get("bezeichnung", ""),
            "schritte": [{"feld": f, "label": l, "wert": werte_.get(f, ""), "erledigt": f in a["erledigt"]}
                         for f, l in kopier.SCHRITTE],
        }

    def assistent_wert(self, text: str) -> dict:
        """Wert für das aktuelle Feld übernehmen (aus der Zwischenablage oder eingetippt)."""
        with self.ass_lock:
            a = self.ass
            if not a or a["fertig"] or not str(text or "").strip():
                return self.assistent_status()
            feld = kopier.SCHRITTE[a["schritt"]][0]
            wert, weitere = kopier.aufbereiten(feld, str(text))
            k = self.sp.kunde(a["kid"])
            daten = k["daten"]
            daten["kunde"][feld] = wert
            daten["kunde"].update(weitere)
            self.sp.aktualisiere(a["kid"], daten=daten)
            a["erledigt"].update([feld, *weitere])
            self._assistent_weiter()
            return self.assistent_status()

    def _assistent_weiter(self) -> None:
        a = self.ass
        a["version"] += 1
        n = a["schritt"] + 1
        while n < len(kopier.SCHRITTE) and kopier.SCHRITTE[n][0] in a["erledigt"]:
            n += 1  # z. B. PLZ/Ort wurde schon zusammen mit der Straße übernommen
        if n >= len(kopier.SCHRITTE):
            a["fertig"] = True
            if self.assistent_fenster_zu:
                threading.Timer(1.2, self.assistent_fenster_zu).start()
        else:
            a["schritt"] = n

    def assistent_aktion(self, aktion: str) -> dict:
        with self.ass_lock:
            a = self.ass
            if not a:
                return self.assistent_status()
            if aktion == "zurueck":
                a["schritt"] = max(0, a["schritt"] - 1)
                a["fertig"] = False
                a["version"] += 1
            elif aktion == "ueberspringen":
                self._assistent_weiter()
            elif aktion == "beenden":
                a["fertig"] = True
                a["version"] += 1
                if self.assistent_fenster_zu:
                    threading.Timer(0.3, self.assistent_fenster_zu).start()
            # Zwischenablage ab jetzt neu beobachten (alter Inhalt zählt nicht)
            a["seq"] = self.ablage.sequenz()
            return self.assistent_status()

    def _assistent_beobachten(self) -> None:
        eigenes = self.ass
        while self.ass is eigenes and not eigenes["fertig"] and not self._stop.is_set():
            seq = self.ablage.sequenz()
            if seq != eigenes["seq"]:
                eigenes["seq"] = seq
                text = self.ablage.text()
                if text and text.strip():
                    self.assistent_wert(text)
            time.sleep(0.25)

    # ---------- Programm-Update ----------
    def update_pruefen(self) -> dict:
        try:
            self.update_info = update.pruefen()
        except update.UpdateFehler as e:
            raise AppFehler(str(e)) from e
        return self.update_info

    def update_installieren(self) -> dict:
        if not update.installiert():
            raise AppFehler("Updates lassen sich nur in der installierten Notfallordner.exe einspielen")
        info = self.update_pruefen()
        if not info["verfuegbar"]:
            raise AppFehler("Sie haben bereits die neueste Version")
        try:
            exe = update.herunterladen_und_tauschen(info)
        except update.UpdateFehler as e:
            raise AppFehler(str(e)) from e
        if self.neustart:
            threading.Timer(1.0, self.neustart, args=(exe,)).start()  # erst antworten, dann neu starten
        return {"version": info["neueste"]}

    def starte_update_pruefung(self) -> None:
        """Einmal beim Start still nach Updates schauen (nur in der installierten .exe)."""
        if not update.installiert():
            return

        def pruefe():
            try:
                self.update_info = update.pruefen()
            except Exception:  # noqa: BLE001 - ohne Internet einfach nichts anzeigen
                pass
        threading.Thread(target=pruefe, daemon=True, name="update").start()

    # ---------- Sicherung ----------
    def sicherung_erstellen(self, passwort: str) -> str:
        if len(passwort or "") < 8:
            raise AppFehler("Das Passwort muss mindestens 8 Zeichen haben")
        ziel = self.ausgabe / "Sicherungen"
        ziel.mkdir(parents=True, exist_ok=True)
        datei = ziel / f"Notfallordner-Sicherung_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.nfo"
        datei.write_bytes(self.sp.sicherung(passwort))
        return str(datei)

    def sicherung_laden(self, inhalt: bytes, passwort: str) -> int:
        try:
            return self.sp.wiederherstellen(inhalt, passwort)
        except ValueError as e:
            raise AppFehler(str(e)) from e
        except Exception as e:  # noqa: BLE001 - z. B. falsches Passwort (InvalidTag)
            raise AppFehler("Passwort falsch oder Datei beschädigt") from e
