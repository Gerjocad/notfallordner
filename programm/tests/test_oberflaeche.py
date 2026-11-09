"""Startet Programmlogik und Oberflächen-Server und prüft die Grundfunktionen über HTTP."""

import json
import urllib.request
from pathlib import Path

from nfo.app import App
from nfo.server import Server
from nfo.speicher import Speicher


def test_server(tmp_path: Path):
    srv = Server(App(Speicher(tmp_path / "d"), tmp_path / "a"))
    srv.start()
    try:
        base = f"http://127.0.0.1:{srv.port}"
        html = urllib.request.urlopen(base + "/").read().decode()
        assert "app.js" in html
        assert "window.NFO" in urllib.request.urlopen(base + "/felder.js").read().decode()
        req = urllib.request.Request(base + "/api/status", data=b"{}", method="POST", headers={"X-Token": srv.token})
        st = json.loads(urllib.request.urlopen(req).read())
        assert st["ok"] and st["daten"]["briefkasten"]["eingerichtet"] is False
        bad = urllib.request.Request(base + "/api/status", data=b"{}", method="POST", headers={"X-Token": "falsch"})
        try:
            urllib.request.urlopen(bad)
            raise AssertionError("ohne Token erlaubt")
        except urllib.error.HTTPError as e:
            assert e.code == 403
        try:
            urllib.request.urlopen(base + "/../nfo/app.py")
            raise AssertionError("Pfad außerhalb von ui erreichbar")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.stop()
