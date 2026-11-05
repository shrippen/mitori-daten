# Mitori Daten — eine Quelle für Heft, App und andere

Die Programmdaten der Aikido-Shinki-Rengo-, Daitoryu- und Itto-den-Shinki-Toho-Prüfungsprogramme
und alles, was eine Anwendung daraus macht: Heft (LuaLaTeX), App Mitori (Qt 6 / Kirigami) und andere
Implementierungen des Datenformats.

Eine Quelle heißt: Daten, Validierung, Generatoren, Video-Bundle-Format und ihre Tests. Der Stil Shinki
gehört zur App und liegt in `mitori-app/shinki/`. Die Videos liegen nie in einem Repo.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `daten/` | Quell-YAML (`aikido.yaml`, `daitoryu.yaml`, `shinki-toho.yaml`, `begriffe.yaml`, `daitoryu-begriffe.yaml`); erzeugte YAMLs (`lexikon.yaml`, `shinki-toho-kommentare.yaml`, `videos.yaml`); `aikido-vorbemerkung.tex`. |
| `quellen/` | Originale (Prüfungsordnungen, Listen, PDFs), von `tools/kommentare.py` und `tools/lexikon.py` gelesen. |
| `tools/` | `daten.py` (prüft + erzeugt `mitori-daten.json` und `*.lua`), `kommentare.py`, `lexikon.py`, `kapitel.py`, `bundle.py` (Video-Bundle-Encoder). |
| `tests/` | `test_daten.py` (Datenformat, Glossar, Wartezeiten), `test_bundle.py` (Bundle-Encoder). |
| `STAND` | Datenstand, den App und Heft anzeigen (`JJJJ.M.N`). |
| `KORREKTUREN.md` | Offene Fragen zu den Daten, mit IDs (`A-…`, `D-…`, `S-…`) und Status. |

`CHANGELOG.md` beschreibt die Daten-Releases.

## Datenstand

Jeder Daten-Release hat eine Nummer `JJJJ.M.N` (z. B. `2026.11.0`), in dieser Reihenfolge:

1. `STAND` und einen Abschnitt `## [JJJJ.M.N] — Datum` in `CHANGELOG.md` per PR ändern.
2. Nach dem Merge taggen: `git tag v2026.11.0 <commit> && git push origin v2026.11.0`.
3. In `mitori-app` und `mitori-heft` das Submodul auf dieses Tag ziehen, in beiden zusammen.

Die App zeigt den Stand unter „Über Mitori“, das Heft auf dem Titel: So fällt auf, wenn beide
verschiedene Daten haben. Die CI hier prüft, dass Tag und `STAND` übereinstimmen; die CI von App und
Heft, dass der Pin auf `main` genau auf dieses Tag zeigt.

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
```

Die CI macht dasselbe. `tools/kapitel.py` und das Packen echter Bundles brauchen die Videos und
laufen lokal.

## Lizenz

GPL-3.0-or-later für Daten, Werkzeuge, Tests, Code. Texte und Listen in `quellen/` und
die daraus übernommenen Kommentare gehören ihren Verfassern (Shinkiryu-Verband).
