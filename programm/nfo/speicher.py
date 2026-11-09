"""Lokaler Speicher: SQLite-Datenbank im Benutzerprofil, Inhalte mit DPAPI geschützt."""

from __future__ import annotations

import io
import json
import os
import secrets
import sqlite3
import sys
import threading
import time
import zipfile
from pathlib import Path

from . import krypto


def standard_ordner() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "Notfallordner"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "notfallordner"


def dokumente_ordner() -> Path:
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # 5 = Eigene Dokumente
            if buf.value:
                return Path(buf.value) / "Notfallordner"
        except Exception:  # noqa: BLE001
            pass
    return Path.home() / "Documents" / "Notfallordner"


class Speicher:
    """Alle Zugriffe laufen über eine Sperre, weil Oberfläche und Briefkasten-Abruf parallel laufen."""

    def __init__(self, ordner: Path | None = None):
        self.ordner = Path(ordner or standard_ordner())
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.ordner / "daten.db", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS einstellungen (schluessel TEXT PRIMARY KEY, wert BLOB);
            CREATE TABLE IF NOT EXISTS kunden (
              id TEXT PRIMARY KEY, erstellt REAL, geaendert REAL, status TEXT,
              einladung TEXT, eingang REAL, ordner_erstellt REAL, neu INTEGER DEFAULT 0, daten BLOB);
            """
        )
        self.db.commit()

    # ----- Einstellungen (geschützt gespeichert) -----
    def setze(self, schluessel: str, wert) -> None:
        with self.lock:
            blob = krypto.schuetzen(json.dumps(wert).encode())
            self.db.execute("REPLACE INTO einstellungen VALUES (?, ?)", (schluessel, blob))
            self.db.commit()

    def hole(self, schluessel: str, standard=None):
        with self.lock:
            row = self.db.execute("SELECT wert FROM einstellungen WHERE schluessel=?", (schluessel,)).fetchone()
        return json.loads(krypto.entschuetzen(row[0])) if row else standard

    # ----- Kunden -----
    def _zeile(self, r) -> dict:
        return {"id": r[0], "erstellt": r[1], "geaendert": r[2], "status": r[3], "einladung": r[4],
                "eingang": r[5], "ordner_erstellt": r[6], "neu": bool(r[7]),
                "daten": json.loads(krypto.entschuetzen(r[8]))}

    def kunden(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM kunden ORDER BY geaendert DESC").fetchall()
        return [self._zeile(r) for r in rows]

    def kunde(self, kid: str) -> dict | None:
        with self.lock:
            r = self.db.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
        return self._zeile(r) if r else None

    def kunde_per_einladung(self, einladung: str) -> dict | None:
        with self.lock:
            r = self.db.execute("SELECT * FROM kunden WHERE einladung=?", (einladung,)).fetchone()
        return self._zeile(r) if r else None

    def neuer_kunde(self, daten: dict, status: str = "neu", einladung: str | None = None) -> dict:
        kid, now = secrets.token_hex(8), time.time()
        with self.lock:
            self.db.execute(
                "INSERT INTO kunden (id, erstellt, geaendert, status, einladung, daten) VALUES (?,?,?,?,?,?)",
                (kid, now, now, status, einladung, krypto.schuetzen(json.dumps(daten).encode())),
            )
            self.db.commit()
        return self.kunde(kid)

    def aktualisiere(self, kid: str, **felder) -> dict | None:
        erlaubt = {"status", "einladung", "eingang", "ordner_erstellt", "neu", "daten"}
        sets, vals = ["geaendert=?"], [time.time()]
        for k, v in felder.items():
            if k not in erlaubt:
                raise KeyError(k)
            if k == "daten":
                v = krypto.schuetzen(json.dumps(v).encode())
            if k == "neu":
                v = int(bool(v))
            sets.append(f"{k}=?")
            vals.append(v)
        with self.lock:
            self.db.execute(f"UPDATE kunden SET {', '.join(sets)} WHERE id=?", (*vals, kid))
            self.db.commit()
        return self.kunde(kid)

    def loesche(self, kid: str) -> None:
        with self.lock:
            self.db.execute("DELETE FROM kunden WHERE id=?", (kid,))
            self.db.commit()

    # ----- Sicherung -----
    def sicherung(self, passwort: str) -> bytes:
        """Alles (Einstellungen, Kunden, Vorlage) als passwortgeschützte Datei."""
        with self.lock:
            einst = {r[0]: json.loads(krypto.entschuetzen(r[1])) for r in self.db.execute("SELECT * FROM einstellungen")}
        inhalt = {"version": 1, "einstellungen": einst, "kunden": self.kunden()}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("daten.json", json.dumps(inhalt))
            vorlage = self.ordner / "vorlage.docx"
            if vorlage.exists():
                z.write(vorlage, "vorlage.docx")
        return krypto.mit_passwort(buf.getvalue(), passwort)

    def wiederherstellen(self, datei: bytes, passwort: str) -> int:
        roh = krypto.ohne_passwort(datei, passwort)
        with zipfile.ZipFile(io.BytesIO(roh)) as z:
            inhalt = json.loads(z.read("daten.json"))
            if "vorlage.docx" in z.namelist():
                (self.ordner / "vorlage.docx").write_bytes(z.read("vorlage.docx"))
        with self.lock:
            self.db.execute("DELETE FROM einstellungen")
            self.db.execute("DELETE FROM kunden")
            for k, v in inhalt["einstellungen"].items():
                self.db.execute("INSERT INTO einstellungen VALUES (?, ?)", (k, krypto.schuetzen(json.dumps(v).encode())))
            for k in inhalt["kunden"]:
                self.db.execute(
                    "INSERT INTO kunden VALUES (?,?,?,?,?,?,?,?,?)",
                    (k["id"], k["erstellt"], k["geaendert"], k["status"], k["einladung"], k["eingang"],
                     k["ordner_erstellt"], int(k["neu"]), krypto.schuetzen(json.dumps(k["daten"]).encode())),
                )
            self.db.commit()
        return len(inhalt["kunden"])
