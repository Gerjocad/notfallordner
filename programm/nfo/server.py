"""Kleiner lokaler Webserver für die Programmoberfläche (nur auf 127.0.0.1, mit Zufalls-Token)."""

from __future__ import annotations

import base64
import hmac
import json
import mimetypes
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .app import App, AppFehler
from .briefkasten import BriefkastenFehler


def ressourcen() -> Path:
    """Ordner mit ui/ und felder.js (im Quellcode oder in der .exe)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def _felder_js() -> Path:
    r = ressourcen()
    for p in (r / "felder.js", r.parent / "gemeinsam" / "felder.js"):
        if p.exists():
            return p
    raise FileNotFoundError("felder.js")


class Server:
    def __init__(self, app: App, port: int = 0):
        self.app = app
        self.token = secrets.token_urlsafe(24)
        handler = self._handler()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.port = self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#t={self.token}"

    def start(self) -> None:
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="ui-server").start()

    def stop(self) -> None:
        self.httpd.shutdown()

    def _handler(self):
        app, srv = self.app, self
        ui = ressourcen() / "ui"

        aktionen = {
            "status": lambda d: app.status(),
            "kunden": lambda d: app.kunden(),
            "kunde": lambda d: app.kunde(d["id"]),
            "kunde_neu": lambda d: app.kunde_neu(d.get("bezeichnung", ""), bool(d.get("mit_link", True))),
            "kunde_speichern": lambda d: app.kunde_speichern(d["id"], d["daten"], d.get("stand")),
            "kunde_loeschen": lambda d: app.kunde_loeschen(d["id"]),
            "gelesen": lambda d: app.gelesen(d["id"]),
            "link_neu": lambda d: app.link_neu(d["id"]),
            "abrufen": lambda d: app.abrufen(),
            "ordner_erstellen": lambda d: app.ordner_erstellen(d["id"], bool(d.get("mit_pdf", True))),
            "oeffnen": lambda d: app.oeffnen(d["pfad"]),
            "berater_speichern": lambda d: app.berater_speichern(d.get("berater") or {}, d.get("datenschutz")),
            "briefkasten_verbinden": lambda d: app.briefkasten_verbinden(d.get("adresse", ""), d.get("zugang", "")),
            "vorlage_setzen": lambda d: app.vorlage_setzen(base64.b64decode(d["inhalt"]), d.get("name", "")),
            "sicherung_erstellen": lambda d: app.sicherung_erstellen(d.get("passwort", "")),
            "update_pruefen": lambda d: app.update_pruefen(),
            "assistent_start": lambda d: app.assistent_start(d["id"]),
            "assistent_status": lambda d: app.assistent_status(),
            "assistent_wert": lambda d: app.assistent_wert(d.get("text", "")),
            "assistent_aktion": lambda d: app.assistent_aktion(d.get("aktion", "")),
            "update_installieren": lambda d: app.update_installieren(),
            "sicherung_laden": lambda d: app.sicherung_laden(base64.b64decode(d["inhalt"]), d.get("passwort", "")),
        }

        class H(BaseHTTPRequestHandler):
            server_version = "Notfallordner"

            def log_message(self, *a):  # keine Konsolenausgabe
                pass

            def _send(self, code: int, body: bytes, typ: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", typ)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                pfad = self.path.split("?")[0]
                if pfad == "/":
                    pfad = "/index.html"
                if pfad == "/felder.js":
                    datei = _felder_js()
                else:
                    datei = (ui / pfad.lstrip("/")).resolve()
                    if ui.resolve() not in datei.parents or not datei.is_file():
                        return self._send(404, b"nicht gefunden", "text/plain")
                typ = mimetypes.guess_type(str(datei))[0] or "application/octet-stream"
                if typ.startswith("text/") or typ.endswith("javascript"):
                    typ += "; charset=utf-8"
                self._send(200, datei.read_bytes(), typ)

            def do_POST(self):  # noqa: N802
                if not hmac.compare_digest(self.headers.get("X-Token", ""), srv.token):
                    return self._send(403, b'{"fehler":"nicht berechtigt"}', "application/json")
                name = self.path.split("?")[0].removeprefix("/api/")
                fn = aktionen.get(name)
                if not fn:
                    return self._send(404, b'{"fehler":"unbekannt"}', "application/json")
                try:
                    laenge = int(self.headers.get("Content-Length", "0"))
                    daten = json.loads(self.rfile.read(laenge) or b"{}") if laenge else {}
                    ergebnis = fn(daten)
                    body = json.dumps({"ok": True, "daten": ergebnis}, ensure_ascii=False).encode()
                    self._send(200, body, "application/json; charset=utf-8")
                except (AppFehler, BriefkastenFehler) as e:
                    self._send(400, json.dumps({"ok": False, "fehler": str(e)}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
                except Exception as e:  # noqa: BLE001
                    self._send(500, json.dumps({"ok": False, "fehler": f"Unerwarteter Fehler: {e}"}, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        return H
