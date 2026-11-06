"""Checks of tools/uebersetzung.py, the page to check the English of the programme data."""
import re
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "tools"))

import daten as werkzeug      # noqa: E402
import uebersetzung           # noqa: E402

STAND = "2026.11.0"


def text(de, en, ort="aikido/k5", bereich="Aikido › Grade"):
    return werkzeug.Text(bereich, ort, "name", de, en)


def zeile(seite, de):
    """The table row that holds a German text."""
    return next(z for z in re.findall(r"<tr class.*?</tr>", seite, re.S) if f'<td lang="de">{de}</td>' in z)


def test_marken():
    """Missing English is marked loudly, the same text in both languages quietly."""
    seite = uebersetzung.seite([text("Waffen", "Weapons"), text("Ikkyo", "Ikkyo"), text("Neu", None)], STAND)
    assert 'data-art="uebersetzt"' in zeile(seite, "Waffen")
    assert '<td class="en" lang="en">Weapons</td>' in zeile(seite, "Waffen")
    assert 'data-art="gleich"' in zeile(seite, "Ikkyo") and '<span class="marke">=</span>' in zeile(seite, "Ikkyo")
    assert 'data-art="fehlt"' in zeile(seite, "Neu") and '<span class="marke">fehlt</span>' in zeile(seite, "Neu")
    for filter_name in ("alle", "uebersetzt", "gleich", "fehlt"):
        assert f'data-filter="{filter_name}"' in seite
    assert "Fehlt (1)" in seite and "Gleich (1)" in seite and "Übersetzt (1)" in seite


def test_gleicher_text_eine_zeile_mit_allen_orten():
    """A name repeated in one group is one row; its other places fold away."""
    seite = uebersetzung.seite([text("Ikkyo", "Ikkyo", "a/1"), text("Ikkyo", "Ikkyo", "a/2"), text("Ikkyo", "Ikkyo", "a/3")], STAND)
    assert len(re.findall(r"<tr class", seite)) == 1
    assert "a/1 · name" in seite and "+2 weitere" in seite and "a/3 · name" in seite
    assert "Alle (1)" in seite


def test_bereiche_gegliedert():
    seite = uebersetzung.seite([text("a", "b", bereich="Aikido › Kyu-Grade › Kata"), text("c", "d", bereich="Glossar › Wörter")], STAND)
    assert ">Aikido</h2>" in seite and "<h3>Kyu-Grade › Kata</h3>" in seite
    assert ">Glossar</h2>" in seite and "<h3>Wörter</h3>" in seite


def test_texte_werden_maskiert():
    seite = uebersetzung.seite([text('<b>"x"</b>', "a & b")], STAND)
    assert "<b>" not in seite and "&lt;b&gt;" in seite and "a &amp; b" in seite


def test_meldet_fehler_der_daten(tmp_path, monkeypatch, capsys):
    """The page shows only missing English; other errors of the data must reach the terminal."""
    monkeypatch.setattr(sys, "argv", ["uebersetzung.py", str(tmp_path / "s.html")])
    monkeypatch.setattr(werkzeug, "erzeuge", lambda ablage: werkzeug.melde("Absätze anders"))
    monkeypatch.setattr(werkzeug, "fehler", [])
    monkeypatch.setattr(werkzeug, "texte", [])
    uebersetzung.main()
    assert "Absätze anders" in capsys.readouterr().err


def test_seite_aus_den_daten_ohne_netz(tmp_path):
    """The whole page from the repository's data: complete, self-contained, in a new folder."""
    ziel = tmp_path / "neu" / "uebersetzung.html"
    subprocess.run([sys.executable, str(WURZEL / "tools" / "uebersetzung.py"), str(ziel)], check=True, capture_output=True)
    seite = ziel.read_text(encoding="utf-8")

    assert "Frontales Abwärtsschlagen aus parallelem Stand" in seite
    assert "Frontal downward strike from a parallel stance" in seite
    assert "Fehlt (0)" in seite
    assert 'data-art="fehlt"' not in seite

    # Offline: nothing that a browser would fetch.
    assert not re.search(r"""(?:src|href)=["'](?!#)|@import|url\(|https?://""", seite)
    assert "default-src 'none'" in seite
