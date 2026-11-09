"""Verbindung zum Online-Briefkasten (Cloudflare Worker).

Der Briefkasten speichert nur verschlüsselte Einsendungen, bis das Programm sie abholt und löscht.
"""

from __future__ import annotations

import json
import secrets
import ssl
import urllib.error
import urllib.request


class BriefkastenFehler(Exception):
    pass


def _ssl_kontext() -> ssl.SSLContext:
    try:
        import certifi  # in der .exe mitgeliefert
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class Briefkasten:
    def __init__(self, adresse: str, zugang: str, timeout: float = 20):
        adresse = (adresse or "").strip().rstrip("/")
        if adresse and not adresse.startswith(("https://", "http://")):
            adresse = "https://" + adresse
        self.adresse, self.zugang, self.timeout = adresse, (zugang or "").strip(), timeout
        self._ssl = _ssl_kontext()

    def _anfrage(self, methode: str, pfad: str, daten=None, admin: bool = True):
        if not self.adresse:
            raise BriefkastenFehler("Keine Briefkasten-Adresse eingestellt")
        body = json.dumps(daten).encode() if daten is not None else None
        req = urllib.request.Request(self.adresse + pfad, data=body, method=methode)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "Notfallordner-Programm/1")
        if admin:
            req.add_header("Authorization", "Bearer " + self.zugang)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl if self.adresse.startswith("https") else None) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise BriefkastenFehler("Zugangsschlüssel falsch") from e
            if e.code == 404:
                raise BriefkastenFehler("Briefkasten unter dieser Adresse nicht gefunden") from e
            raise BriefkastenFehler(f"Briefkasten antwortet mit Fehler {e.code}") from e
        except urllib.error.URLError as e:
            raise BriefkastenFehler("Briefkasten nicht erreichbar – Internetverbindung prüfen") from e
        except (TimeoutError, OSError) as e:
            raise BriefkastenFehler("Briefkasten nicht erreichbar – Internetverbindung prüfen") from e

    def pruefen(self) -> dict:
        return self._anfrage("GET", "/api/admin/ping")

    def schluessel_hinterlegen(self, pub_b64: str, kid: str, berater: dict | None = None) -> None:
        self._anfrage("PUT", "/api/admin/key", {"pub": pub_b64, "kid": kid, "berater": berater or {}})

    def einladung_anlegen(self) -> tuple[str, str]:
        """Neue Einladung -> (ID, Link für den Kunden)."""
        eid = secrets.token_urlsafe(18)
        self._anfrage("POST", "/api/admin/invite", {"id": eid})
        return eid, f"{self.adresse}/f/{eid}"

    def einladung_loeschen(self, eid: str) -> None:
        self._anfrage("DELETE", f"/api/admin/invite/{eid}")

    def link(self, eid: str) -> str:
        return f"{self.adresse}/f/{eid}"

    def posteingang(self, voll: bool = False) -> list[dict]:
        return self._anfrage("GET", "/api/admin/inbox" + ("?voll=1" if voll else "")).get("items", [])

    def abgeholt(self, eid: str) -> None:
        self._anfrage("DELETE", f"/api/admin/inbox/{eid}")
