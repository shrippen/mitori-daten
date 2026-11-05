# mitori-daten

Programmdaten, Quellen, Werkzeuge und Shinki-Stil. `mitori-app` und `mitori-heft` binden das Repo
als Submodul ein und pinnen einen Stand.

- Programmdaten nur in `daten/*.yaml` ändern, dann `python3 tools/daten.py`; offene Fragen als `[ID]`,
  jede ID steht in `KORREKTUREN.md`.
- `daten/shinki-toho-kommentare.yaml` und `daten/lexikon.yaml` sind erzeugt, nie von Hand bearbeiten.
- **Videos kommen nie ins Repo**, auch nicht verschlüsselt. Ebenso keine Bundle-Schlüssel und Codes.
- Vor dem Commit die Checks aus `README.md`. Bugfix: erst der Test, der fehlschlägt.
- Nach dem Merge: in App und Heft das Submodul nachziehen, erst danach dort pushen.
