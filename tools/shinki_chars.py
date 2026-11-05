#!/usr/bin/env python3
"""Sammelt die japanischen Zeichen aus Textdateien für tools/shinki_fonts.py.

  python3 tools/shinki_chars.py daten shinki/qml <app>/app/qml <app>/app/i18n <app>/app \\
      --ausgabe shinki/fonts/chars-full.txt
"""
import argparse
import sys
from pathlib import Path

# Nur Quelltext: ein PDF oder eine Schrift als Text gelesen ergibt Tausende falscher Kanji.
TEXT = {".yaml", ".qml", ".js", ".ts", ".cpp", ".h"}

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
            if not datei.is_file() or datei.suffix not in TEXT:
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
