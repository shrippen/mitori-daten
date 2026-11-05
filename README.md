# Mitori Daten — eine Quelle für Heft, App und andere

Die Programmdaten der Aikido-Shinki-Rengo-, Daitoryu- und Itto-den-Shinki-Toho-Prüfungsprogramme
und alles, was eine Anwendung daraus macht: Heft (LuaLaTeX), App Mitori (Qt 6 / Kirigami) und andere
Implementierungen des Datenformats.

Eine Quelle heißt: Daten, Validierung, Generatoren, Video-Bundle-Format, Shinki-Stil (Bibel, Tokens,
QML-Komponenten, Schriften) und ihre Tests.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `daten/` | Quell-YAML (`aikido.yaml`, `daitoryu.yaml`, `shinki-toho.yaml`, `begriffe.yaml`, `daitoryu-begriffe.yaml`); erzeugte YAMLs (`lexikon.yaml`, `shinki-toho-kommentare.yaml`, `videos.yaml`); `aikido-vorbemerkung.tex`. |
| `quellen/` | Originale (Prüfungsordnungen, Listen, PDFs), von `tools/kommentare.py` und `tools/lexikon.py` gelesen. |
| `tools/` | `daten.py` (prüft + erzeugt `mitori-daten.json` und `*.lua`), `kommentare.py`, `lexikon.py`, `kapitel.py`, `bundle.py` (Video-Bundle-Encoder), `shinki_style.py`, `shinki_fonts.py`, `shinki_chars.py`. |
| `shinki/` | Shinki-Stil (neben Kante): Bibel (`README.md`), Werte (`tokens.json`), QML-Komponenten (`qml/Shinki/`), Schriften (`fonts/`). |
| `tests/` | `test_daten.py` (Datenformat, Glossar, Wartezeiten), `test_bundle.py` (Bundle-Encoder), `test_shinki.py` (Kontrast, Schriftfamilien). |
| `KORREKTUREN.md` | Offene Fragen zu den Daten, mit IDs (`A-…`, `D-…`, `S-…`) und Status. |

`CHANGELOG.md` beschreibt die Daten-Releases.

## Verwendung

### Mitori-App (Schwester-Repo) als Submodul

Im App-Repo wird `mitori-daten` als Git-Submodul unter `third_party/mitori-daten/` referenziert.
Der Build ruft `${MITORI_DATA_DIR}/tools/daten.py` auf, um `mitori-daten.json` zu erzeugen; der
CMake-Default zeigt auf den Submodul-Pfad.

### Mitori-Heft (Schwester-Repo)

Auch das Heft-Repo bindet `mitori-daten` als Submodul ein. `heft/build.sh` ruft das gleiche
`tools/daten.py` auf, um die `*.lua`-Dateien für die LuaLaTeX-Satzvorlage zu erzeugen.

### Andere Implementierungen

Eine andere Implementierung des Datenformats (z. B. eine zweite App) muss nur
`mitori-daten.json` lesen können. Schema-Version steht im Feld `format`
(siehe `tests/test_daten.py`). Wer Video-Bundles entschlüsseln will: das Format ist im Docstring
von `tools/bundle.py` dokumentiert; die Referenz-Implementierung und die C++-App-Implementierung
sind untereinander kompatibel.

## Checks

Vor jedem Commit:

```sh
python3 tools/daten.py
python3 -m pytest -q tests
python3 tools/kommentare.py > /dev/null
python3 tools/lexikon.py > /dev/null
git diff --exit-code -- daten/
python3 tools/shinki_style.py --check
```

Die CI macht dasselbe. `tools/kapitel.py` und das Packen echter Bundles brauchen die Videos und
laufen lokal.

## Schriftzeichen-Pipeline

`shinki/fonts/NotoSerifJP-Regular-Subset.ttf` hat nur die Zeichen, die die App zeigt (sonst 13 MB);
sie stehen in `shinki/fonts/chars-full.txt`. Wer ein neues Kanji einführt, fährt beides neu, von
einem App-Checkout aus:

```sh
python3 tools/shinki_chars.py daten shinki/qml <app>/app --ausgabe shinki/fonts/chars-full.txt
python3 tools/shinki_fonts.py <google/fonts>
```

`tests/test_shinki.py` prüft Daten und Stil, `tests/test_shinki_font.py` im App-Repo die App.

## Lizenz

GPL-3.0-or-later für Daten, Werkzeuge, Tests, Stil, Code. Texte und Listen in `quellen/` und
die daraus übernommenen Kommentare gehören ihren Verfassern (Shinkiryu-Verband).
