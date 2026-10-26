# Vokabel-Übersetzer

Eine Übersetzer-App im Stil des Apple-Übersetzers, gebaut zum Englisch-Lernen beim Lesen:
jedes Wort, das du nachschlägst, wird automatisch als Vokabel gespeichert und später mit
Karteikarten nach einem Wiederholungsplan (Spaced Repetition, wie Anki) abgefragt.

**Sofort nutzen:** https://claude.ai/artifact/LQusJiDEaPP2uvoWKZP1qr
(in Safari öffnen → Teilen → „Zum Home-Bildschirm“)

## Was die App kann

| Tab | Funktion |
| --- | --- |
| **Übersetzen** | Englisch ⇄ Deutsch wie im Apple-Übersetzer, schon beim Tippen. Wörter kommen sofort aus dem **eingebauten Wörterbuch** (offline, kostenlos): Bedeutungen nach Wortart, Nomen mit Artikel, Wendungen, Grundform (*glimpsed → glimpse*, *ran → run*), Aussprache. Mit dem ✦-Knopf übersetzt **Claude auf Wunsch** – ganze Sätze oder die Bedeutung im Satz aus dem Buch. Wörter und kurze Wendungen (bis 4 Wörter) werden automatisch gespeichert; bei ganzen Sätzen kannst du jedes Wort einzeln antippen. |
| **Kamera** | Buchseite fotografieren (Text wird von Claude erkannt) oder einen Absatz einfügen. Jedes Wort ist antippbar, der Satz wird als Kontext mitgespeichert, bereits gespeicherte Wörter sind unterstrichen. |
| **Üben** | Karteikarten (Nochmal / Schwer / Gut / Einfach), **Schreiben** (deutsche Bedeutung sehen, englisches Wort tippen, Tippfehler werden erkannt) und **Auswahl** (Multiple Choice). Richtung EN→DE, DE→EN oder gemischt. Tagesziel, Serie (Tage in Folge), Wochenübersicht, freies Üben. |
| **Vokabeln** | Alle Wörter nach Datum, Suche, Filter (Fällig / Neu / Am Lernen / Gefestigt), Details mit Lernstand, Bearbeiten, Löschen. |

Weitere Details:

- **Erneut nachgeschlagen?** Dann zählt die App mit („3× nachgeschlagen“) und holt das Wort sofort zurück in die Wiederholung.
- **Lernplan:** neue Karten in Schritten von 1 und 10 Minuten, danach 1 Tag, und dann wachsende Abstände (SM-2). Der Lerntag beginnt um 4 Uhr, damit spätes Lesen noch zu „heute“ zählt.
- **Export:** JSON-Backup und CSV (für Anki/Excel); Import aus dem JSON-Backup.
- Hell- und Dunkelmodus, iPhone-Safe-Areas, Systemschrift (auf dem iPhone SF Pro).

## Zwei Varianten, ein Code

`src/app.html` ist die ganze App (HTML, CSS und JavaScript ohne Abhängigkeiten). Sie läuft auf zwei Arten:

1. **Als claude.ai-Artifact** (Link oben) – die empfohlene Variante.
   - Wörter: eingebautes Wörterbuch, verbraucht kein Claude-Kontingent. (Artifacts dürfen keine fremden Übersetzungsdienste aufrufen, deshalb liegt das Wörterbuch direkt in der App.)
   - Sätze, Wörter ohne Eintrag, Kontext-Bedeutung und Foto-Texterkennung: Claude, nur wenn du den ✦-Knopf bzw. „Seite fotografieren“ antippst. Beim ersten Mal fragt claude.ai, ob die App Claude verwenden darf → „Erlauben“.
   - Vokabeln liegen in deinem Claude-Konto und sind auf allen Geräten gleich.
2. **Als eigenständige Web-App (PWA)** in `docs/` – für jeden statischen Webspace.
   - Wörter aus dem eingebauten Wörterbuch; Sätze und fehlende Wörter über Google Übersetzer (Fallback: MyMemory).
   - Vokabeln liegen im Browser des Geräts (Backup über Export/Import).
   - Funktioniert offline (Service Worker), Mikrofon-Eingabe und „Einfügen“-Knopf, `?q=wort` im Link übersetzt direkt.
   - Hosting z. B. mit GitHub Pages: Repository-Einstellungen → *Pages* → *Deploy from a branch* → `main` / `/docs`.
     (Für private Repositories braucht GitHub Pages ein bezahltes Konto; alternativ das Repository öffentlich machen.)

### Schneller nachschlagen aus der Lese-App (iPhone)

- **Kopieren & Einsetzen:** Wort im E-Book markieren → *Kopieren* → App öffnen → ins Feld tippen → *Einsetzen*. Die Übersetzung startet sofort und das Wort ist gespeichert.
- **Kurzbefehl (nur PWA-Variante):** In der Kurzbefehle-App einen Kurzbefehl anlegen: *Im Teilen-Menü anzeigen* (Typ Text) → *URL öffnen* mit `https://<deine-adresse>/?q=` + *Kurzbefehleingabe*. Danach steht der Kurzbefehl im Teilen-Menü von Apple Books & Co.

## Entwicklung

```sh
python3 tools/build_dict.py <pfad>/de-en   # Wörterbuch → docs/dict/ (Ding aus dem Ubuntu-Paket trans-de-en; pip install wordfreq)
node tools/build.mjs     # baut docs/ (PWA) aus src/app.html
node tools/icons.cjs     # rendert die App-Icons aus docs/icons/icon.svg (braucht Playwright)
```

Änderungen immer in `src/app.html` machen und danach `docs/` neu bauen.

## Wörterbuch

Die Wörterbuchdaten stammen aus **Ding** (Englisch–Deutsch, © Frank Richter, TU Chemnitz,
https://dict.tu-chemnitz.de/, GPL 2 oder später). `tools/build_dict.py` sortiert die Bedeutungen
(Alltagsbedeutungen vor Fachsprache, Slang und Regionalem; Worthäufigkeit über `wordfreq`), ordnet
gebeugte Formen ihrer Grundform zu und teilt alles in kleine Dateien unter `docs/dict/`, von denen
die App nur die gerade benötigte lädt.
