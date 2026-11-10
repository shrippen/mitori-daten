# Lernpakete

Ein Lernpaket ist ein Video-Bundle mit eigenen Techniken: Lernvideos, die zu keiner Prüfung gehören.
Die Techniken gibt es nur mit den Videos. Darum stehen sie nicht in `mitori-daten.json` und nicht im
Heft, sondern verschlüsselt im Bundle (`inhalt.mvb`). Die App zeigt sie, solange das Paket geladen ist.

Je Paket eine Datei `pakete/<id>.yaml`; die Id ist der Dateiname und zugleich die Bundle-Id
(`a-z`, `0-9`, Bindestriche). `tools/paket.py` prüft alle Pakete (auch `tools/daten.py` und die CI),
`tools/bundle.py build <id>` baut eins wie ein Prüfungs-Bundle.

```yaml
titel: Shirakawa · Irimi Tenkan        # in der App-Liste; öffentlich im Manifest
titel_en: …                             # nur, wo das Englische abweicht (gilt für jedes Feld x / x_en)
sparte: aikido                          # Glossar für die Kanji: aikido, daitoryu, shinkitoho
text: …                                 # optional, kurze Beschreibung (mit text_en)
videos:
  - id: shirakawa-1/video               # Videoschlüssel; Ordner-sicher, eindeutig über alle Pakete
    datei: "Ordner/Video.mp4"           # relativ zu --videos von bundle.py
    titel: Vol. 1 · Irimi Tenkan
    beschnitt: {hoehe: 1080, y: 0, h: 1080, verhaeltnis: 1.7778}   # optional, wie in videos.yaml
abschnitte:
  - titel: Grundtechniken
    titel_en: Basic techniques
    text: …                             # optional
    techniken:
      - id: shomen-uchi-irimi-nage      # eindeutig im Paket; in der App lern/<paket>/<id>
        name: Irimi-nage                # Technik, wie im Programm geschrieben (Kanji aus dem Glossar)
        angriff: Shomen-uchi            # optional
        zusatz: …                       # optional, Ausführung (mit zusatz_en)
        text: …                         # optional, was das Video zeigt (mit text_en)
        wie: [aikido/kyu-grade/…/k5/irimi-nage-2]   # optional: dieselbe Technik im Prüfungsprogramm
        video: shirakawa-1/video
        von: 129.0                      # Sekunden
        bis: 152.6
```

`tools/paket.py entwurf <untertitel> --video <key>` schreibt aus Untertiteln (SRT oder WebVTT) einen
Entwurf: kurze Zeilen (Einblendungen) werden Techniken mit `pruefen: true` in einem Abschnitt „Entwurf“;
Abschnitte und Namen von Hand. Die Zeiten von Hand am Video prüfen,
dann das Feld löschen. Ein Paket mit `pruefen` baut `bundle.py` nicht.

## Inhalt im Bundle (`inhalt.mvb`, verschlüsselt wie ein Video)

JSON, `format` 1; Texte wie in `mitori-daten.json` mit `x_en` nur, wo es abweicht:

```json
{"format": 1, "id": "shirakawa-1", "titel": "…", "sparte": "aikido", "text": "…",
 "videos": [{"id": "shirakawa-1/video", "titel": "…", "beschnitt": {…}}],
 "abschnitte": [{"titel": "…", "text": "…", "techniken": [
   {"id": "lern/shirakawa-1/shomen-uchi-irimi-nage", "name": "Irimi-nage", "jp": "入身投げ",
    "angriff": {"name": "Shomen-uchi", "jp": "正面打ち"}, "zusatz": "…", "text": "…",
    "wie": ["aikido/…"], "video": "shirakawa-1/video", "von": 129.0, "bis": 152.6}]}]}
```

Im öffentlichen Manifest steht ein Lernpaket unter `lernpakete` (nicht `bundles`: Mitori bis 0.3.0
kennt nur diese), wie ein Bundle, aber ohne `kapitel` (die Stellen verraten die Techniken) und mit
`inhalt: {datei, format, groesse, sha256, klar, url}`; kennt die App das `format` nicht, lädt sie das Paket
nicht und bittet um ein Update. Codes stehen wie bei jedem Bundle unter `codes`.
