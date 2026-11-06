#!/usr/bin/env python3
"""Schreibt eine HTML-Seite zum Gegenprüfen: jeder deutsche Text der Programmdaten neben seinem Englisch.

Aufruf aus dem Projektordner:  python3 tools/uebersetzung.py AUSGABE.html

Eingabe:  dieselben Daten wie tools/daten.py (die Texte und ihre Orte sammelt es dort beim Erzeugen).
Ausgabe:  eine Datei, offline lesbar, ohne Anfragen nach außen; nicht einchecken.
Marken:   „fehlt“ (kein Englisch; tools/daten.py bricht dann auch ab), „=“ (beide Sprachen gleich, bei
          Namen meist richtig). Die Seite wird auch mit fehlendem Englisch geschrieben, dafür ist sie da.
Glossar der Übersetzung: tools/uebersetzung-glossar.md
"""
import argparse
import html
import sys
import tempfile
from collections import Counter
from pathlib import Path

import daten

FEHLT = "fehlt"
GLEICH = "gleich"
UEBERSETZT = "uebersetzt"
EBENE = " › "

# Kante (Kante/tokens/palette.json, Gruvbox dunkel), hier kopiert: Das Repo kennt Kante nicht, und das
# Stylesheet unter shrippen.github.io würde die Seite vom Netz abhängig machen. Rajdhani nur, wenn installiert.
STIL = """
:root { --bg-void: #141312; --bg0: #282828; --bg1: #3c3836; --bg2: #504945; --bg-panel: #2a2826;
  --fg0: #fbf1c7; --fg1: #ebdbb2; --fg3: #a89984; --accent: #e8dcc4; --cyan: #5ccfc4; --orange: #fe8019;
  --mono: "JetBrains Mono", "Fira Code", "Cascadia Code", Consolas, monospace;
  --kopf: Rajdhani, system-ui, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg-void); color: var(--fg1); font: 15px/1.5 system-ui, sans-serif; }
header { position: sticky; top: 0; z-index: 1; background: var(--bg0); border-bottom: 1px solid var(--bg2);
  padding: 12px 20px; }
h1, h2, h3 { font-family: var(--kopf); font-weight: 600; text-transform: uppercase; letter-spacing: .08em;
  color: var(--fg0); margin: 0; }
h1 { font-size: 20px; }
h2 { font-size: 22px; margin: 32px 0 8px; scroll-margin-top: 96px; }
h3 { font-size: 15px; margin: 20px 0 6px; color: var(--accent); }
main { padding: 0 20px 48px; }
nav { margin-top: 16px; font-size: 13px; }
nav a { color: var(--cyan); margin-right: 12px; }
.zeile { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 8px; }
.stand, .zahl, .ort, .marke, button { font-family: var(--mono); font-size: 12px; }
.stand, .ort { color: var(--fg3); }
button { background: var(--bg1); color: var(--fg1); border: 1px solid var(--bg2); padding: 4px 10px; cursor: pointer; }
button[aria-pressed=true] { border-color: var(--cyan); color: var(--cyan); }
input { background: var(--bg-void); color: var(--fg1); border: 1px solid var(--bg2); padding: 4px 8px; min-width: 16em; }
button:focus-visible, input:focus-visible, a:focus-visible, summary:focus-visible { outline: 2px solid var(--cyan); }
table { width: 100%; border-collapse: collapse; table-layout: fixed; background: var(--bg-panel); }
th { font: 12px var(--mono); text-transform: uppercase; letter-spacing: .14em; color: var(--fg3); text-align: left; }
th, td { padding: 6px 10px; border-bottom: 1px solid var(--bg1); vertical-align: top; }
th:first-child { width: 22%; }
th:last-child { width: 39%; }
td { white-space: pre-wrap; overflow-wrap: anywhere; }
td.ort { white-space: normal; }
.gleich td.en { color: var(--fg3); }
.fehlt td.en { background: var(--bg1); }
.marke { color: var(--fg3); margin-left: 6px; }
.fehlt .marke { color: var(--orange); font-weight: 700; }
details { margin-top: 2px; }
summary { cursor: pointer; }
"""

# Filter und Suche; ein Abschnitt ohne sichtbare Zeile verschwindet mit.
SKRIPT = """
const knoepfe = [...document.querySelectorAll('button[data-filter]')];
const suche = document.querySelector('input');
let filter = 'alle';

function zeige() {
  const wort = suche.value.toLowerCase();
  for (const z of document.querySelectorAll('tr[data-art]')) {
    z.hidden = (filter !== 'alle' && z.dataset.art !== filter) || !z.textContent.toLowerCase().includes(wort);
  }
  for (const a of document.querySelectorAll('section')) {
    a.hidden = !a.querySelector('tr[data-art]:not([hidden])');
  }
}

for (const k of knoepfe) {
  k.onclick = () => {
    filter = k.dataset.filter;
    knoepfe.forEach(b => b.setAttribute('aria-pressed', b === k));
    zeige();
  };
}
suche.oninput = zeige;
"""


def art(text):
    """Marke einer Zeile."""
    if text.en is None:
        return FEHLT
    return GLEICH if text.en == text.de else UEBERSETZT


def zusammenfassen(texte):
    """Gruppiert nach Bereich; derselbe Text steht in einem Bereich nur einmal, mit allen Orten.
    {bereich: {(de, en): [(ort, feld), …]}}; so bleibt „Ikkyo“ eine Zeile je Technikgruppe."""
    bereiche = {}
    for t in texte:
        bereiche.setdefault(t.bereich, {}).setdefault((t.de, t.en), []).append((t.ort, t.feld))
    return bereiche


def orte_html(orte):
    """Der erste Ort; weitere eingeklappt, Technikgruppen haben sonst Listen über Bildschirme."""
    als_text = [html.escape(f"{ort} · {feld}") for ort, feld in orte]
    if len(orte) == 1:
        return als_text[0]
    weitere = "<br>".join(als_text[1:])
    return f"{als_text[0]}<details><summary>+{len(orte) - 1} weitere</summary>{weitere}</details>"


def zeile_html(de, en, orte):
    if en is None:
        marke, klasse, zelle = "fehlt", FEHLT, ""
    elif en == de:
        marke, klasse, zelle = "=", GLEICH, html.escape(en)
    else:
        marke, klasse, zelle = "", UEBERSETZT, html.escape(en)
    zeichen = f'<span class="marke">{marke}</span>' if marke else ""
    return (f'<tr class="{klasse}" data-art="{klasse}"><td class="ort">{orte_html(orte)}</td>'
            f'<td lang="de">{html.escape(de)}</td><td class="en" lang="en">{zelle}{zeichen}</td></tr>')


def abschnitt_html(bereich, zeilen):
    """Ein Bereich als Tabelle unter seiner Überschrift ohne die oberste Ebene (die ist h2)."""
    titel = EBENE.join(bereich.split(EBENE)[1:]) or bereich
    koerper = "\n".join(zeile_html(de, en, orte) for (de, en), orte in zeilen.items())
    return (f"<section><h3>{html.escape(titel)}</h3><table><thead><tr><th>Ort</th><th>Deutsch</th>"
            f"<th>English</th></tr></thead><tbody>\n{koerper}\n</tbody></table></section>")


def seite(texte, stand):
    """Die ganze Seite als Text; Zahlen zählen Texte, nicht Orte."""
    bereiche = zusammenfassen(texte)
    zahl = Counter(art(t) for t in {(t.de, t.en): t for t in texte}.values())
    oben = {}
    for bereich, zeilen in bereiche.items():
        oben.setdefault(bereich.split(EBENE)[0], []).append(abschnitt_html(bereich, zeilen))

    koerper = []
    verweise = []
    for i, (titel, abschnitte) in enumerate(oben.items()):
        verweise.append(f'<a href="#b{i}">{html.escape(titel)}</a>')
        koerper.append(f'<h2 id="b{i}">{html.escape(titel)}</h2>' + "\n".join(abschnitte))

    knoepfe = [("alle", f"Alle ({sum(zahl.values())})", "true"),
               (UEBERSETZT, f"Übersetzt ({zahl[UEBERSETZT]})", "false"),
               (GLEICH, f"= Gleich ({zahl[GLEICH]})", "false"),
               (FEHLT, f"Fehlt ({zahl[FEHLT]})", "false")]
    knopf_html = "".join(f'<button type="button" data-filter="{f}" aria-pressed="{g}">{html.escape(t)}</button>'
                         for f, t, g in knoepfe)
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>Mitori: Übersetzung der Programmdaten</title>
<style>{STIL}</style>
</head>
<body>
<header>
<h1>Übersetzung der Programmdaten</h1>
<div class="zeile"><span class="stand">Datenstand {html.escape(stand)}</span>{knopf_html}<input type="search" placeholder="Suchen" aria-label="Suchen"></div>
</header>
<main>
<nav>{"".join(verweise)}</nav>
{"".join(koerper)}
</main>
<script>{SKRIPT}</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ausgabe", type=Path, help="Pfad der HTML-Datei")
    ziel = ap.parse_args().ausgabe

    # Die Ausgaben von daten.py braucht hier niemand, nur die Texte, die es dabei sammelt.
    with tempfile.TemporaryDirectory() as ablage:
        daten.erzeuge(Path(ablage))

    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(seite(daten.texte, daten.datenstand()), encoding="utf-8")
    fehlen = sum(1 for t in daten.texte if t.en is None)
    print(f"uebersetzung: {len(daten.texte)} Stellen, {fehlen} ohne Englisch → {ziel}", file=sys.stderr)

    # Die Seite zeigt nur fehlendes Englisch; andere Fehler der Daten sollen nicht „alles da“ vortäuschen.
    if daten.fehler:
        print("\n".join(["Fehler in den Daten:"] + [f"  {f}" for f in daten.fehler]), file=sys.stderr)


if __name__ == "__main__":
    main()
