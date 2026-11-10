"""Start: python -m nfo   (oder Notfallordner.exe)

Optionen:
  --browser       Oberfläche im normalen Browser statt im Programmfenster öffnen
  --daten ORDNER  anderer Datenordner (zum Testen)
  --port N        fester Port (zum Testen)
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
import webbrowser
from pathlib import Path

from . import update

from .app import App
from .server import Server
from .speicher import Speicher

EINZELSTART_PORT = 47613


def _schon_offen(warten: float = 0) -> socket.socket | None:
    """Verhindert, dass das Programm zweimal läuft (zwei Abrufe würden sich stören).
    Nach einem Update wartet die neue Version kurz, bis die alte beendet ist."""
    ende = time.time() + warten
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", EINZELSTART_PORT))
            s.listen(1)
            return s
        except OSError:
            s.close()
            if time.time() >= ende:
                return None
            time.sleep(0.5)


def _meldung(text: str) -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Notfallordner", 0x40)
    else:
        print(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="Notfallordner")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--daten", type=Path)
    ap.add_argument("--ausgabe", type=Path)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--kein-abruf", action="store_true")
    ap.add_argument("--ohne-fenster", action="store_true", help="nur den Hintergrunddienst starten (für Tests)")
    ap.add_argument("--nach-update", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    sperre = _schon_offen(20 if args.nach_update else 0)
    if sperre is None:
        _meldung("Das Programm Notfallordner läuft bereits.")
        return 1

    update.aufraeumen()
    app = App(Speicher(args.daten) if args.daten else None, args.ausgabe)
    server = Server(app, args.port)
    server.start()
    if not args.kein_abruf:
        app.starte_abruf()
    app.starte_update_pruefung()

    def neustart(exe: Path) -> None:
        app.stop()
        sperre.close()  # Sperre freigeben, damit die neue Version starten kann
        update.neu_starten(exe)
        os._exit(0)
    app.neustart = neustart

    if args.ohne_fenster:
        print(f"Notfallordner läuft: {server.url}", flush=True)
        import threading
        threading.Event().wait()

    if not args.browser:
        try:
            import webview  # pywebview: eigenes Programmfenster (Edge WebView2)
            webview.create_window("Notfallordner", server.url, width=1320, height=900, min_size=(900, 640))
            klein = {"w": None}

            def assistent_auf() -> bool:
                if klein["w"] is not None:
                    try:
                        klein["w"].destroy()
                    except Exception:  # noqa: BLE001
                        pass
                url = server.url.replace("/#t=", "/assistent.html#t=")
                klein["w"] = webview.create_window("Kopier-Assistent", url, width=400, height=560,
                                                   on_top=True, resizable=True, min_size=(340, 420))
                return True

            def assistent_zu() -> None:
                if klein["w"] is not None:
                    try:
                        klein["w"].destroy()
                    except Exception:  # noqa: BLE001
                        pass
                    klein["w"] = None
            app.assistent_fenster, app.assistent_fenster_zu = assistent_auf, assistent_zu
            webview.start()
            app.stop()
            return 0
        except Exception:  # noqa: BLE001 - kein WebView2: Browser verwenden
            pass

    print(f"Notfallordner läuft: {server.url}")
    webbrowser.open(server.url)
    try:
        import threading
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    app.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
