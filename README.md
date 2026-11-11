# Mitori Daten — eine Quelle für Heft, App und andere

Die Programmdaten der Aikido-Shinki-Rengo-, Daitoryu- und Itto-den-Shinki-Toho-Prüfungsprogramme
und die Werkzeuge, die sie prüfen und für Anwendungen aufbereiten: Heft (`mitori-heft`), App
(`mitori-app`) und andere Implementierungen des Datenformats.

Eine Quelle heißt: Daten, Validierung, Generatoren, Video-Bundle-Format und ihre Tests. Der Stil Shinki
gehört zur App und liegt in `mitori-app/shinki/`. Die Videos liegen nie in einem Repo.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `daten/` | Quell-YAML (`aikido.yaml`, `daitoryu.yaml`, `shinki-toho.yaml`, `begriffe.yaml`, `daitoryu-begriffe.yaml`); erzeugte YAMLs (`lexikon.yaml`, `shinki-toho-kommentare.yaml`, `videos.yaml`); Englisch (`englisch-*.yaml`); `aikido-vorbemerkung.tex`. |
| `quellen/` | Originale (Prüfungsordnungen, Listen, PDFs), von `tools/kommentare.py` und `tools/lexikon.py` gelesen. |
| `tools/` | `daten.py` (prüft + erzeugt `mitori-daten.json` und `*.lua`), `kommentare.py`, `lexikon.py`, `kapitel.py`, `bundle.py` (Video-Bundle-Encoder, auch für Lernpakete), `paket.py` (prüft Lernpakete, erzeugt ihren Inhalt und Entwürfe aus Untertiteln; Aufbau in `lernpakete.md`, die Pakete liegen außerhalb des Repos), `uebersetzung.py` (Prüfseite Deutsch–Englisch, Glossar dazu in `uebersetzung-glossar.md`). |
| `tests/` | `test_daten.py` (Datenformat, Glossar, Wartezeiten), `test_bundle.py` (Bundle-Encoder), `test_paket.py` (Lernpakete), `test_uebersetzung.py` (Prüfseite). |
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
(siehe `tests/test_daten.py`). Die Videos lädt sie wie Mitori, siehe „Video-Bundles“.

## Video-Bundles

Die Prüfungsvideos sind verschlüsselt und frei herunterladbar. Öffnen kann man sie nur mit einem
Code (eine Lizenz je DVD, vom Verband). Jede App, die dieses Format umsetzt, kann dieselben
Videos und Codes nutzen. Referenz: `tools/bundle.py` (Python, libsodium) und
`mitori-app/app/store/bundlecrypto.cpp` (C++, Monocypher). Beide sind zueinander kompatibel.
Lernpakete (Bundles mit eigenen Techniken) beschreibt `tools/lernpakete.md`.

### Ablauf

```
Manifest laden ──► Code eingeben ──► Eintrag finden ──► Inhaltsschlüssel auspacken
                                                              │
  Datei laden (url) ──► Blöcke entschlüsseln, sha256 mitrechnen ──► Video (meist MKV, HEVC)
```

1. **Manifest:** `https://git.arianw.de/api/packages/shrippen/generic/mitori-manifest/1/manifest.json`.
   Es ist öffentlich und enthält weder Codes noch Schlüssel. Es nennt nur die aktuelle Version
   jedes Bundles, alte Dateien verschwinden vom Server.
2. **Code** normalisieren: Großbuchstaben, ohne Bindestriche und Leerzeichen, `O`→`0`,
   `I` und `L`→`1`. Ergebnis: 20 Zeichen Crockford-Base32 (`0-9A-Z` ohne `ILOU`), 19 zufällige
   (95 Bit) und ein Prüfzeichen. Angezeigt wird er in Fünfergruppen: `7KQ2M-X9HDV-3TAPR-WE6YT`.
   Das Prüfzeichen ist Luhn mod 32. Es wird von rechts über die ersten 19 Zeichen gerechnet:
   Faktor 2, 1, 2, …, `summe += w // 32 + w % 32` mit `w = Faktor × Wert`,
   Prüfzeichen `(32 − summe % 32) % 32`.
3. **Kennung** = `hex(BLAKE2b-128("mitori-code:" + code))`. Sie ist der Schlüssel in `codes`.
   Fehlt sie, ist der Code falsch oder gesperrt.
4. **Inhaltsschlüssel auspacken:**
   `kek = Argon2id(passwort = code, salz, t Durchläufe, m KiB, 1 Spur) → 32 Byte`.
   `roh = base64-dekodiert(schluessel)` = Nonce (24 Byte) + Geheimtext + Tag (16 Byte).
   `inhaltsschluessel = XChaCha20-Poly1305-IETF-open(roh, AD = "mitori-key:" + bundle, kek)`
   ergibt 32 Byte. `t` und `m` vor dem Rechnen begrenzen. Mitori nimmt `t` 1–16 und `m` 8 KiB–256 MiB, mehr gilt als beschädigt.
   Der Schlüssel bleibt über alle Versionen eines Bundles gleich: Wer ihn einmal hat, lädt neue
   Versionen ohne Code.
5. **Datei** von `url` laden und dabei Stück für Stück entschlüsseln (Format unten) und sha256
   mitrechnen. Am Ende müssen `groesse` und `sha256` (der verschlüsselten Datei) stimmen, sonst
   die Datei verwerfen. Heraus kommen `klar` Byte, meist MKV mit HEVC. Mit von Hand fertigen
   Videos bleibt der Container der Quelle (z. B. MP4), also nicht voraussetzen.

### Dateiformat (`.mvb`)

```
"MITORIV1" (8) │ Präfix (16) │ Block 0 │ Block 1 │ … │ letzter Block
Block = XChaCha20-Poly1305-IETF(Klartext ≤ 1 MiB) + Tag (16)
```

- Klartext je Block 1 MiB, der letzte kürzer. Eine leere Datei hat einen leeren Block.
- Nonce = Präfix + Index (8 Byte, little endian), Index ab 0.
- AD = `"mitori-chunk"` + Index (8 Byte LE) + 1 Byte (`1` beim letzten Block, sonst `0`).
- Der letzte Block ergibt sich aus der Dateigröße. Ein abgeschnittener oder umgestellter Download
  scheitert so an der Prüfung. Entschlüsseln geht im Strom, während der Download läuft.

### Manifest

```json
{"format": 2,
 "bundles": [{"id": "aikido-kyu", "version": 2, "titel": "Aikido · alle Kyu", "hinweis": "",
   "videos": [{"video": "aikido/k5", "datei": "aikido-k5.mvb",
               "url": "https://…/aikido-kyu/2/aikido-k5.mvb",
               "groesse": 123, "sha256": "…", "klar": 120, "beschnitten": true, "bilder": 3000,
               "kapitel": [{"id": "aikido/…/ikkyo-1", "von": 302.32, "bis": 343.64}]}]}],
 "lernpakete": [ … wie bundles, ohne "kapitel", mit "inhalt" (tools/lernpakete.md) … ],
 "codes": {"<Kennung>": {"bundle": "aikido-kyu", "salz": "<base64, 16 Byte>",
                          "t": 3, "m": 65536, "schluessel": "<base64>"}}}
```

| Feld | Bedeutung |
|---|---|
| `video` | Videoschlüssel, derselbe wie in `videos` von `mitori-daten.json` |
| `groesse`, `sha256` | der verschlüsselten Datei |
| `klar` | Größe nach dem Entschlüsseln |
| `beschnitten` | `true`: Die schwarzen Ränder mit Titeln sind schon weg. `beschnitt` aus `mitori-daten.json` nicht mehr anwenden. |
| `bilder` | Anzahl der Bilder (zur Prüfung) |
| `kapitel` | Stellen der Techniken (Ids aus `mitori-daten.json`, Sekunden) in genau dieser Datei. Sie gelten vor `video.von/bis` aus `mitori-daten.json`, die zu den Originalen der DVD gehören. Mit der Datei zusammen speichern. |

Unbekannte Felder überlesen. Ein anderes `format` als 2 nicht lesen. Mitori behält dann das zuletzt geladene Manifest.
Gesperrte Codes fehlen in `codes`. Einen Schlüssel, der schon auf einem Gerät liegt, nimmt das
nicht zurück.

Beispiele für jeden Schritt: `tests/test_bundle.py`. Testdaten mit bekanntem Code und Schlüssel:
`mitori-app/app/tests/data/bundle/`.

## Englisch

Die Texte bleiben deutsch in den Quellen. Das Englisch steht in `daten/englisch-programm.yaml`,
`englisch-kommentare.yaml`, `englisch-lexikon.yaml` (Paare `{de, en}`, Schlüssel ist der deutsche Text selbst) und
`englisch-gleich.yaml` (Texte, die gleich bleiben, meist japanische Namen). `tools/daten.py` bricht ab, wenn ein
Text kein Englisch hat, die Absätze nicht passen oder ein Eintrag zu keinem Text mehr gehört: Ändert sich ein deutscher
Text, muss sein Paar mit. In `mitori-daten.json` steht neben einem Feld `x` das Feld `x_en`, nur wenn es sich
unterscheidet (im Glossar neben `de` das Feld `en`); `FORMAT` bleibt, weil nur Felder dazukommen. Das Heft bleibt deutsch.

Zum Gegenprüfen schreibt `python3 tools/uebersetzung.py AUSGABE.html` eine Seite mit beiden Sprachen nebeneinander
(offline lesbar, nicht einchecken).

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
