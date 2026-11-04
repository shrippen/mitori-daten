#!/usr/bin/env python3
"""Sammelt japanische Zeichen aus den gegebenen Verzeichnissen und schreibt sie sortiert und
eindeutig in eine Textdatei (eine Zeile, durch Leerzeichen getrennt), so dass sie als Argument
für tools/shinki_fonts.py dienen kann. So muss shinki_fonts.py keinen Pfad in die App oder das
Heft kennen.

Aufruf:
  python3 tools/shinki_chars.py daten/ quellen/ tools/ shinki/ tests/ \
      > build/shinki/daten-chars.txt

Welche Zeichen zählen: Kana, CJK-Ideogramme, Kana-Satzzeichen und ähnliches
(siehe is_japanese). Quelldateien, die nicht gelesen werden können, fallen
leise aus: das Werkzeug übersieht z. B. keine Binärdatei.
"""
import argparse
import sys
from pathlib import Path

# Kana, Kana-Erweiterung, Kanji (CJK), CJK-Kompatibilität und voller
# Halbbreiten-Block. Werkzeug des shinki-Stils; shinki_fonts.py prüft dagegen.
JAPANESE_RANGES = [
    (0x3000, 0x30FF),   # Kana und Kana-Satzzeichen
    (0x3400, 0x4DBF),   # CJK-Erweiterung A
    (0x4E00, 0x9FFF),   # CJK-Ideogramme (BMP)
    (0xF900, 0xFAFF),   # CJK-Kompatibilität
    (0xFF00, 0xFFEF),   # Halbbreite Formen
]


def is_japanese(c):
    """Wahr, wenn c in einem der japanischen Unicode-Bereiche liegt."""
    o = ord(c)
    return any(lo <= o <= hi for lo, hi in JAPANESE_RANGES)


def collect(paths):
    chars = set()
    for root in paths:
        if not root.exists():
            sys.stderr.write(f"shinki_chars: fehlt {root}\n")
            continue
        for datei in root.rglob("*"):
            if not datei.is_file():
                continue
            try:
                text = datei.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            chars |= {c for c in text if is_japanese(c)}
    return "".join(sorted(chars))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ordner", nargs="+", type=Path, help="Verzeichnisse, die durchsucht werden")
    ap.add_argument("--ausgabe", type=Path, help="Datei statt stdout")
    args = ap.parse_args()
    text = collect(args.ordner)
    sys.stdout.write(text + "\n")
    if args.ausgabe:
        args.ausgabe.parent.mkdir(parents=True, exist_ok=True)
        # git versteht keine Zeile ohne Newline am Ende.
        args.ausgabe.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
