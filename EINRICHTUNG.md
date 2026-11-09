# Notfallordner-Programm einrichten

Diese Anleitung ist für den Berater. Die Einrichtung dauert etwa 20 Minuten und ist nur einmal nötig.

## Wie es funktioniert

1. Im Programm auf **„+ Neuer Kunde“** klicken und die Daten des Kunden sowie seinen Hausarzt eintragen.
2. **„Link für Notfallkontakte“** klicken und den Link per E-Mail oder WhatsApp an den Kunden schicken.
3. Der Kunde trägt nur seine Notfallkontakte ein. Sie werden **schon auf seinem Gerät verschlüsselt** und
   landen im „Briefkasten“, einem kleinen kostenlosen Online-Dienst bei Cloudflare.
4. Das Programm schaut jede Minute in den Briefkasten, holt neue Einsendungen ab, entschlüsselt sie und
   **löscht sie danach im Briefkasten**. Gespeichert wird alles nur auf Ihrem PC.
5. Kunde öffnen, prüfen, **„Notfallordner erstellen“**: Word und PDF liegen danach in
   `Dokumente\Notfallordner\<Name, Vorname>\`.

Im Briefkasten liegt nur unlesbarer, verschlüsselter Datensalat, und das nur bis zur Abholung (höchstens
30 Tage). Lesen kann ihn nur Ihr Programm, auch Cloudflare nicht.

---

## Schritt 1: Programm installieren

1. `Notfallordner.exe` in einen eigenen Ordner legen, in dem Sie Dateien speichern dürfen, zum Beispiel
   `Dokumente\Notfallordner-Programm\` oder auf den Desktop. **Nicht** unter `C:\Programme`: Dort fehlen
   meist die Rechte, damit sich das Programm selbst aktualisieren kann.
2. Doppelklick. Beim ersten Start zeigt Windows eventuell **„Der Computer wurde durch Windows geschützt“**,
   weil das Programm nicht von einer bekannten Firma signiert ist. Dann auf **„Weitere Informationen“** und
   **„Trotzdem ausführen“** klicken.
3. Das Programm öffnet die Einrichtung. Tragen Sie zuerst **Ihre Beraterdaten** ein und speichern Sie sie.

Für die PDF-Erstellung nutzt das Programm **Microsoft Word**, falls installiert. Sonst wird das kostenlose
[LibreOffice](https://de.libreoffice.org/download/download/) benötigt.

## Schritt 2: Kostenloses Cloudflare-Konto anlegen

1. Auf <https://dash.cloudflare.com/sign-up> mit Ihrer E-Mail-Adresse ein Konto anlegen und die E-Mail bestätigen.
2. Es wird **keine Kreditkarte** und **keine eigene Internetadresse** benötigt.

## Schritt 3: Speicher (KV) anlegen

1. Im Cloudflare-Dashboard links **„Storage & Databases“ → „Workers KV“** öffnen.
2. **„Create“** (Namespace erstellen), Name: `notfallordner`, speichern.

## Schritt 4: Briefkasten (Worker) anlegen

1. Links **„Workers & Pages“** öffnen, **„Create“** → **„Create Worker“** (bzw. „Hello World“-Vorlage).
2. Name: `notfallordner`, dann **„Deploy“**.
3. **„Edit code“** öffnen, den gesamten vorhandenen Code löschen und den Inhalt der Datei
   **`worker.js`** einfügen (die Datei bekommen Sie zusammen mit dem Programm). Oben rechts **„Deploy“**.
4. Zurück zum Worker, Reiter **„Settings“** → **„Bindings“** → **„Add“** → **„KV namespace“**:
   - Variable name: `NFO`
   - KV namespace: `notfallordner`
   - Speichern.
5. Im Programm unter **Einstellungen → 2. Briefkasten** auf **„Neuen Zugangsschlüssel erzeugen“** klicken
   und den Schlüssel kopieren.
6. Bei Cloudflare im Worker unter **„Settings“** → **„Variables and Secrets“** → **„Add“**:
   - Type: **Secret**
   - Variable name: `ADMIN_TOKEN`
   - Value: den kopierten Zugangsschlüssel einfügen
   - Speichern bzw. **„Deploy“**.
7. Die Adresse des Workers steht oben auf seiner Übersichtsseite, etwa
   `https://notfallordner.IHRNAME.workers.dev`. Kopieren.

## Schritt 5: Programm mit dem Briefkasten verbinden

1. Im Programm unter **Einstellungen → 2. Briefkasten** die Adresse aus Schritt 4.7 eintragen.
   Der Zugangsschlüssel steht schon im Feld.
2. **„Verbinden und testen“** klicken. Bei Erfolg erscheint „✓ Verbunden“.
   Das Programm hinterlegt dabei automatisch seinen öffentlichen Schlüssel im Briefkasten.

| Meldung | Lösung |
|---|---|
| Zugangsschlüssel falsch | Den Schlüssel bei Cloudflare (`ADMIN_TOKEN`) und im Programm vergleichen. Nach dem Ändern bei Cloudflare „Deploy“ klicken. |
| Briefkasten unter dieser Adresse nicht gefunden | Adresse prüfen. Sie endet auf `.workers.dev`, ohne `/` am Ende. |
| Briefkasten antwortet mit Fehler 500 | Die KV-Verknüpfung fehlt oder heißt nicht genau `NFO` (Schritt 4.4). |

## Schritt 6: Word-Vorlage wählen

Unter **Einstellungen → 3. Word-Vorlage** die Datei `02_Notfallordner_2.5_VornameNachname.docx` wählen.
Das Programm speichert eine Kopie, die Originaldatei wird nicht verändert.

## Schritt 7: Ausprobieren

1. **„+ Neuer Kunde“**, Ihren eigenen Namen eingeben, **„Anlegen + Link erstellen“**.
2. Den Link auf dem Handy öffnen, einen Test-Notfallkontakt eintragen, absenden.
3. Spätestens nach einer Minute erscheint der Eintrag im Programm mit roter Markierung
   (oder sofort mit **„Jetzt prüfen“**).

---

## Updates

Unter **Einstellungen → Programm-Update** auf **„Nach Updates suchen“** klicken. Gibt es eine neue Version,
erscheint **„Jetzt aktualisieren“**: Das Programm lädt sie herunter, prüft die Datei, ersetzt sich selbst
und startet neu. Kunden und Einstellungen bleiben erhalten. Beim Programmstart sucht es außerdem still
nach Updates; dann steht in der Seitenleiste „Einstellungen · Update“.

Ändert sich der Briefkasten (`worker.js`) mit einem Update, steht das in den Update-Hinweisen. Dann den
neuen Code wie in Schritt 4.3 bei Cloudflare einfügen.

## Datensicherung

Alle Daten liegen nur auf diesem PC (in `%APPDATA%\Notfallordner`, geschützt mit Ihrem Windows-Konto).
Geht der PC kaputt, sind sie weg. Deshalb regelmäßig unter **Einstellungen → Sicherung erstellen** eine
Sicherung anlegen und auf einen USB-Stick oder in Ihren OneDrive-Ordner kopieren. Die Sicherung ist mit
Ihrem Passwort verschlüsselt. **Ohne das Passwort lässt sie sich nicht öffnen.**

Auf einem neuen PC: Programm starten, **Einstellungen → Sicherung wiederherstellen**.

## Datenschutz

Sie sammeln sensible Kundendaten (IBAN, Steuer-ID, Gesundheitsangaben). Klären Sie bitte vorab mit tecis
bzw. Ihrem Datenschutzbeauftragten, ob Sie die Daten auf diese Weise erheben und speichern dürfen. Im
Kundenformular erscheint ein Einverständnis mit Ihrem Namen und Ihrer E-Mail-Adresse als Verantwortlichem.
Einen eigenen Datenschutzhinweis können Sie in den Einstellungen hinterlegen.
