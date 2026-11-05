# mitori-daten

Programmdaten, Quellen und Werkzeuge. `mitori-app` und `mitori-heft` binden das Repo
als Submodul ein und pinnen einen Stand.

- Programmdaten nur in `daten/*.yaml` ändern, dann `python3 tools/daten.py`; offene Fragen als `[ID]`,
  jede ID steht in `KORREKTUREN.md`.
- `daten/shinki-toho-kommentare.yaml` und `daten/lexikon.yaml` sind erzeugt, nie von Hand bearbeiten.
- **Videos kommen nie ins Repo**, auch nicht verschlüsselt. Ebenso keine Bundle-Schlüssel und Codes.
- Vor dem Commit die Checks aus `README.md`. Bugfix: erst der Test, der fehlschlägt.
- Datenstand: `STAND` (`JJJJ.M.N`) und ein Abschnitt in `CHANGELOG.md`. App und Heft zeigen ihn an und
  pinnen auf `main` nur getaggte Stände.
- Nach dem Merge: Commit taggen (`v<Stand>`), in App und Heft das Submodul auf dieses Tag ziehen, beide zusammen.
