"""Selbst-Update der Notfallordner.exe.

Ablauf:
1. update.json von der Update-Adresse laden: {"version", "url", "sha256", "hinweise"}.
2. Neue .exe neben die laufende herunterladen und die Prüfsumme kontrollieren.
3. Laufende .exe umbenennen (unter Windows erlaubt, auch während sie läuft),
   neue .exe an ihre Stelle legen, neu starten. Die alte Datei wird beim nächsten Start gelöscht.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import __version__
from .briefkasten import _ssl_kontext

# Öffentliche Adresse der neuesten update.json (GitHub-Release „latest“).
# Beim Bauen der .exe schreibt GitHub Actions die Adresse des eigenen Repositorys nach _quelle.py.
try:
    from ._quelle import UPDATE_URL as _GEBAUT  # type: ignore
except ImportError:
    _GEBAUT = "https://github.com/Gerjocad/notfallordner/releases/latest/download/update.json"
UPDATE_URL = os.environ.get("NFO_UPDATE_URL", _GEBAUT)


class UpdateFehler(Exception):
    pass


def _version(v: str) -> tuple:
    teile = []
    for x in str(v).lstrip("vV").split("."):
        try:
            teile.append(int(x))
        except ValueError:
            teile.append(0)
    return tuple(teile + [0] * (3 - len(teile)))


def installiert() -> bool:
    """Nur die gebaute .exe unter Windows kann sich selbst ersetzen."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def _laden(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"Notfallordner/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_kontext()) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateFehler("Noch keine Version zum Herunterladen veröffentlicht") from e
        raise UpdateFehler(f"Update-Server antwortet mit Fehler {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateFehler("Update-Server nicht erreichbar – Internetverbindung prüfen") from e


def pruefen(url: str = UPDATE_URL) -> dict:
    try:
        info = json.loads(_laden(url, 15))
    except json.JSONDecodeError as e:
        raise UpdateFehler("Update-Information ist fehlerhaft") from e
    neu = str(info.get("version", ""))
    return {
        "aktuell": __version__,
        "neueste": neu,
        "verfuegbar": bool(neu) and _version(neu) > _version(__version__),
        "hinweise": str(info.get("hinweise", ""))[:2000],
        "url": info.get("url", ""),
        "sha256": str(info.get("sha256", "")).lower(),
        "installierbar": installiert(),
    }


def herunterladen_und_tauschen(info: dict, exe: Path | None = None) -> Path:
    """Lädt die neue Version und ersetzt die laufende .exe. Gibt den Pfad der (neuen) .exe zurück."""
    if not info.get("url") or len(info.get("sha256", "")) != 64:
        raise UpdateFehler("Update-Information unvollständig")
    exe = Path(exe or sys.executable).resolve()
    neu = exe.with_name(exe.stem + ".update.exe")
    alt = exe.with_name(exe.stem + ".alt.exe")
    daten = _laden(info["url"], 300)
    if hashlib.sha256(daten).hexdigest() != info["sha256"]:
        raise UpdateFehler("Download beschädigt (Prüfsumme stimmt nicht). Bitte später erneut versuchen.")
    try:
        neu.write_bytes(daten)
    except OSError as e:
        raise UpdateFehler(f"Keine Schreibrechte im Programmordner {exe.parent}. "
                           "Bitte die Notfallordner.exe in einen eigenen Ordner legen, z. B. auf den Desktop.") from e
    try:
        if alt.exists():
            alt.unlink()
        exe.rename(alt)
    except OSError as e:
        neu.unlink(missing_ok=True)
        raise UpdateFehler("Die laufende Programmdatei konnte nicht ersetzt werden") from e
    try:
        neu.rename(exe)
    except OSError as e:
        alt.rename(exe)  # zurückrollen
        raise UpdateFehler("Die neue Programmdatei konnte nicht eingesetzt werden") from e
    return exe


def neu_starten(exe: Path) -> None:
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    subprocess.Popen([str(exe), "--nach-update"], creationflags=flags, close_fds=True)


def aufraeumen() -> None:
    """Beim Start: Überbleibsel eines früheren Updates löschen."""
    if not installiert():
        return
    exe = Path(sys.executable).resolve()
    for p in (exe.with_name(exe.stem + ".alt.exe"), exe.with_name(exe.stem + ".update.exe")):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
