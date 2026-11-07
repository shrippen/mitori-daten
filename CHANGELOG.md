# Changelog

## [Unreleased]

## [2026.11.1] — 2026-11-07

Die Programme haben jetzt englische Texte, und die Videos lassen sich für den Download vorbereiten.
An den deutschen Texten ändert sich nichts.

### Neu

- Alle Texte der Programmdaten auf Englisch: Bezeichnungen, Kommentare zu Shinki Toho, Glossar.
  `mitori-daten.json` trägt sie als zusätzliche Felder (`x_en`). Wo der Text gleich bleibt (meist
  japanische Namen), steht nur das deutsche Feld.
- `tools/uebersetzung.py` schreibt eine Seite mit beiden Sprachen nebeneinander zum Gegenprüfen.
  Das Werkzeug nennt dabei auch andere Fehler in den Daten.
- `tools/bundle.py` bereitet die Videos verschlüsselt für den Download per Lizenz vor. Die Videos
  werden statisch auf einem Webserver liegen. Das Manifest mit ihren Adressen und den Schnittpunkten
  je Technik erzeugt `bundle.py`, `bundle.py hochladen` legt es als Paket auf Gitea ab. Hochgeladen
  ist noch nichts.
- Offene Frage S-16: Welche Techniken prüft Shoden?

### Hinweis

- Die englischen Texte sind eine erste Übersetzung und noch nicht gegengelesen.
- `bundle.py` bricht ab, statt ein abgeschnittenes Video, falsche Schnittpunkte oder ein
  unvollständiges Manifest auszuliefern.

## [2026.11.0] — 2026-11-05

Der erste getaggte Datenstand, seit die Daten in einem eigenen Repo liegen. Die Programme selbst sind
unverändert.

### Neu

- Datenstand in der Datei `STAND`. App und Heft zeigen ihn an, so fällt auf, wenn beide
  verschiedene Daten haben.

### Verbessert

- Das Repo enthält nur noch Daten: Der Stil Shinki liegt jetzt in `mitori-app`.
- Die Bundle-Tests laufen in der CI, die Platzhalter-Tests sind weg.

### Hinweis

- `quellen/shinki-news/` ist entfernt. Kein Werkzeug las die PDF.
