# Changelog

## [Unreleased]

## [2026.11.1] — 2026-11-07

Die Programme haben jetzt englische Texte, und die Videos lassen sich für den Download vorbereiten.
An den deutschen Texten ändert sich nichts.

### Neu

- Englische Texte für die Programme und das Glossar, neben den deutschen. Apps, die Englisch zeigen,
  fallen auf Deutsch zurück, wo eine Übersetzung fehlt.
- Eine Prüfseite (`tools/uebersetzung.py`) zeigt Deutsch und Englisch nebeneinander, mit Glossar.
  Von dort lassen sich Fehler in den Daten melden.
- `tools/bundle.py` bereitet die Videos verschlüsselt für den Download per Lizenz vor. Die Videos
  liegen statisch auf einem Webserver, das Manifest mit ihren Adressen und den Schnittpunkten je
  Technik kommt aus diesem Repo. Hochgeladen ist noch nichts.
- Offene Frage S-16: Welche Techniken prüft Shoden?

### Hinweis

- Die englischen Texte sind eine erste Übersetzung und noch nicht gegengelesen.
- `bundle.py` bricht ab, statt ein abgeschnittenes Video, falsche Schnittpunkte oder ein
  unvollständiges Manifest auszuliefern.

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
