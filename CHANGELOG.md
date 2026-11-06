# Changelog

## [Unreleased]

### Neu

- Alle Texte der Programmdaten auf Englisch: Bezeichnungen, Kommentare zu Shinki Toho, Glossar.
  `mitori-daten.json` trägt sie als zusätzliche Felder (`x_en`), die Namen der Techniken bleiben japanisch.
- `tools/uebersetzung.py` schreibt eine Seite mit beiden Sprachen nebeneinander zum Gegenprüfen.

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
