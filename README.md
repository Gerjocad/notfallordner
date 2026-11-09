# Notfallordner

Windows-Programm für Berater: Kundendaten erfassen, Notfallkontakte per Link vom Kunden einholen
(Ende-zu-Ende verschlüsselt) und daraus den Notfallordner als Word und PDF erstellen.
Einrichtung für Berater: siehe [EINRICHTUNG.md](EINRICHTUNG.md). Fertige Programmversionen: unter „Releases“.

| Ordner | Inhalt |
|---|---|
| `programm/` | Windows-Programm (Python): Kundenliste, Briefkasten-Abruf, Word/PDF erstellen, Sicherung |
| `briefkasten/` | Cloudflare Worker: Kundenformular + verschlüsselter Briefkasten |
| `gemeinsam/felder.js` | Felder und Prüfungen, genutzt von Formular und Programm |
| `EINRICHTUNG.md` | Schritt-für-Schritt-Anleitung für den Berater |

Ablauf: Berater erfasst Kunde und Hausarzt, Programm erstellt Einladungslink → Kunde trägt seine Notfallkontakte ein, Daten werden im Browser mit dem
öffentlichen Schlüssel des Programms verschlüsselt (RSA-OAEP-3072 + AES-256-GCM) → Briefkasten speichert
nur den verschlüsselten Umschlag → Programm holt ab, entschlüsselt, speichert lokal (DPAPI) und löscht
im Briefkasten → „Notfallordner erstellen“ füllt die Word-Vorlage (MERGEFIELD/IF) und erzeugt die PDF
über Microsoft Word (sonst LibreOffice).

Entwickeln/Testen:

```
cd programm && pip install -r requirements.txt && python -m pytest tests
python -m nfo --browser                       # Programm im Browser starten
cd ../briefkasten && node build.mjs           # dist/worker.js bauen
node lokal.mjs 8787 <token>                   # Briefkasten lokal (KV im Speicher)
```

Die `.exe` baut GitHub Actions (`.github/workflows/notfallordner.yml`, Artefakt „Notfallordner-Windows“).

**Neue Version veröffentlichen:** `__version__` in `programm/nfo/__init__.py` erhöhen und `programm/hinweise.txt`
anpassen, dann pushen. Der Workflow baut die `.exe`, erstellt `update.json` (Version, Download-Adresse,
SHA-256, Hinweise) und legt ein GitHub-Release `v<Version>` an – **nur wenn das Repository öffentlich ist**,
denn die installierten Programme laden Updates ohne Zugangsdaten von
`https://github.com/<Repository>/releases/latest/download/update.json`.
