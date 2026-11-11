#!/usr/bin/env python3
"""Lernpakete: Video-Bundles mit eigenen Techniken (Aufbau: tools/lernpakete.md).

Aufruf aus dem Projektordner:
  python3 tools/paket.py [pruefen]                  prüft jedes <PAKETE>/*.yaml (auch in tools/daten.py)
  python3 tools/paket.py inhalt <id>                der Inhalt des Pakets als JSON (das steckt verschlüsselt im Bundle)
  python3 tools/paket.py entwurf <untertitel> --video <schluessel> [--id <paket>]
                                                    YAML-Entwurf aus SRT oder WebVTT, von Hand zu prüfen
  python3 tools/paket.py vorschau <id> [--videos <ordner>]
                                                    drei Standbilder je Technik und eine index.html unter
                                                    <GEHEIM>/arbeit/<id>/vorschau/, um die Zeiten zu prüfen

Ein Lernpaket kommt nie in mitori-daten.json oder die *.lua: Die Techniken gibt es nur mit den Videos.
Ein Paket mit `pruefen: true` an einer Technik ist ein Entwurf: Es besteht die Prüfung, `bundle.py build`
baut es nicht.

Entwurf, die Heuristik: Eine Untertitelzeile ist ein Kandidat für eine Technik, wenn sie kurz ist (höchstens
KANDIDAT_WOERTER Wörter), nicht mit .?! endet und mit Großbuchstabe oder Ziffer beginnt (wie eine Überschrift:
„Shomen-uchi Irimi-nage“, nicht „und dann dreht er sich.“). Dieselbe Zeile direkt nach sich selbst zählt einmal.
`von` ist der Beginn der Zeile, `bis` der Beginn des nächsten Kandidaten, beim letzten das Ende des
letzten Untertitels.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daten  # noqa: E402

WURZEL = daten.WURZEL
# Die Pakete liegen nicht im Repo (sein Spiegel ist öffentlich): Ihre Techniken gibt es nur mit den Videos.
GEHEIM = Path(os.environ.get("MITORI_BUNDLE_GEHEIM", WURZEL.parent / "mitori-bundle-geheim"))
PAKETE = Path(os.environ.get("MITORI_PAKETE", GEHEIM / "pakete"))
BUNDLES = WURZEL / "tools" / "bundles.yaml"
FORMAT = 1                                      # des Inhalts im Bundle (inhalt.mvb)
VORSATZ = "lern/"                               # Vorsatz der Technik-Ids
ABSCHNITT_ENTWURF = "Entwurf"
VORSCHAU_ORDNER = "arbeit"                      # unter GEHEIM: <id>/vorschau/
VORSCHAU_BREITE = 320                           # Pixel der Standbilder
VORSCHAU_RAND = 1.0                             # Sekunden hinter von und vor bis
VORSCHAU_QUALITAET = "4"                        # ffmpeg -q:v (2 beste, 31 schlechteste)
VORSCHAU_CSS = ("body{font:14px sans-serif;margin:1em;background:#fff;color:#111}"
                "h2{margin:1.5em 0 .3em}.t{border-top:1px solid #ccc;padding:.5em 0}"
                ".t p{margin:.1em 0}.pruefen{color:#b00;font-weight:bold}"
                ".bilder{display:flex;gap:.5em;flex-wrap:wrap}.bilder figure{margin:0}"
                ".bilder figcaption{font-size:12px;color:#555}")

# Wie bundle.ID: Ids werden Ordnernamen in der App (nur a-z, 0-9 und Bindestriche).
ID = re.compile(r"[a-z0-9][a-z0-9-]*")
VIDEO_ID = re.compile(r"[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*")
SPRACHE = re.compile(r"[a-z]{2}")                # ISO 639-1

# Je Sparte das Glossar der Kanji, wie tools/daten.py es für das Programm nimmt: (Datei, Bausteine).
SPARTEN = {"aikido": ("begriffe.yaml", False), "shinkitoho": ("begriffe.yaml", False),
           "daitoryu": ("daitoryu-begriffe.yaml", True)}

# Felder; zu jedem Feld in MIT_ENGLISCH darf `<feld>_en` stehen, aber nur neben dem Feld.
MIT_ENGLISCH = {"titel", "text", "name", "angriff", "zusatz"}
PAKET_FELDER = {"titel", "sparte", "text", "videos", "abschnitte"}
VIDEO_FELDER = {"id", "datei", "titel", "beschnitt", "untertitel"}
UNTERTITEL_FELDER = {"datei", "sprache"}
ABSCHNITT_FELDER = {"titel", "text", "techniken"}
TECHNIK_FELDER = {"id", "name", "angriff", "zusatz", "text", "wie", "video", "von", "bis", "pruefen"}
TECHNIK_PFLICHT = ("id", "name", "video", "von", "bis")

KANDIDAT_WOERTER = 6
SATZENDE = ".?!"
ENDE = "-->"
ZEIT = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})")
MARKE = re.compile(r"<[^>]*>")
KOPF_BLOECKE = ("WEBVTT", "NOTE", "STYLE", "REGION")
VTT_KOPF = "WEBVTT"
ZEIT_KOMMA = re.compile(r"(\d{1,2}:\d{2}),(\d{3})")


# ── Laden und Prüfen ──

def eintrags_ids(disziplinen):
    """Die Ids aller Einträge des Programms (Techniken, Suburi, Ô-dachi, Kamae, Kiriotoshi)."""
    ids = set()
    for d in disziplinen:
        ids.update(t["id"] for t in d.get("techniken", []))
        for art in ("suburi", "odachi"):
            ids.update(e["id"] for e in d.get(art, []))
        for art in ("kamae", "kiriotoshi"):
            if art in d:
                ids.add(d[art]["id"])
    return ids


def laden():
    """Alle <PAKETE>/*.yaml: ({id: Inhalt}, Fehler beim Lesen). Die Id ist der Dateiname."""
    pakete, fehler = {}, []
    for datei in sorted(PAKETE.glob("*.yaml")):
        try:
            pakete[datei.stem] = yaml.safe_load(datei.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            fehler.append(f"{datei.name}: kein gültiges YAML ({e})")
    return pakete, fehler


def programmdaten():
    """(Ids der Einträge, Videoschlüssel der Prüfungsvideos) aus build/daten/mitori-daten.json."""
    pfad = daten.WURZEL / "build" / "daten" / "mitori-daten.json"
    if not pfad.exists():
        subprocess.run([sys.executable, str(WURZEL / "tools" / "daten.py")])
    j = json.loads(pfad.read_text(encoding="utf-8"))
    return eintrags_ids(j["disziplinen"]), set(j["videos"])


def felder_fehler(wo, d, erlaubt, pflicht=()):
    """Unbekannte und fehlende Felder, ein x_en ohne x."""
    if not isinstance(d, dict):
        return [f"{wo}: kein Eintrag mit Feldern"]
    fehler = [f"{wo}: {k} fehlt" for k in pflicht if k not in d]
    for k in d:
        if k in erlaubt:
            continue
        grund = k[:-3] if k.endswith("_en") else None
        if grund in erlaubt and grund in MIT_ENGLISCH:
            if grund not in d:
                fehler.append(f"{wo}: {k} ohne {grund}")
            elif d[k] == d[grund]:      # x_en nur, wo das Englische abweicht
                fehler.append(f"{wo}: {k} gleich {grund}")
            continue
        fehler.append(f"{wo}: unbekanntes Feld {k}")
    return fehler


def zahl(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def liste_fehler(wo, d, feld):
    """Eine nichtleere Liste unter `feld`, sonst die Fehlermeldung."""
    if not isinstance(d.get(feld), list) or not d[feld]:
        return [f"{wo}: {feld} fehlt oder ist leer"]
    return []


def untertitel_fehler(wo, v):
    """Die Untertitel eines Videos: Liste aus datei (relativ) und sprache (ISO 639-1), je Sprache eine."""
    if "untertitel" not in v:
        return []
    liste = v["untertitel"]
    if not isinstance(liste, list) or not liste:
        return [f"{wo}: untertitel ist keine nichtleere Liste"]
    fehler, sprachen = [], set()
    for u in liste:
        fehler += felder_fehler(f"{wo}, Untertitel", u, UNTERTITEL_FELDER, ("datei", "sprache"))
        if not isinstance(u, dict):
            continue
        datei = u.get("datei")
        if "datei" in u:
            pfad = Path(datei) if isinstance(datei, str) and datei else None
            if pfad is None or pfad.is_absolute() or ".." in pfad.parts:
                fehler.append(f"{wo}, Untertitel: datei nur relativ zu --videos, ohne ..")
        sprache = u.get("sprache")
        if "sprache" not in u:
            continue
        if not isinstance(sprache, str) or not SPRACHE.fullmatch(sprache):
            fehler.append(f"{wo}, Untertitel: sprache aus zwei Kleinbuchstaben (ISO 639-1)")
        elif sprache in sprachen:
            fehler.append(f"{wo}, Untertitel: sprache {sprache} steht doppelt")
        sprachen.add(sprache)
    return fehler


def video_fehler(pid, d, belegt, pruefung):
    fehler = liste_fehler(pid, d, "videos")
    erklaert = set()
    for v in d.get("videos") or []:
        wo = f"{pid}, Video {v.get('id') if isinstance(v, dict) else v}"
        fehler += felder_fehler(wo, v, VIDEO_FELDER, ("id", "datei", "titel"))
        if isinstance(v, dict):
            fehler += untertitel_fehler(wo, v)
        if not isinstance(v, dict) or "id" not in v:
            continue
        datei = Path(str(v.get("datei")))
        if datei.is_absolute() or ".." in datei.parts:
            fehler.append(f"{wo}: datei nur relativ zu --videos, ohne ..")
        vid = v["id"]
        if not isinstance(vid, str) or not VIDEO_ID.fullmatch(vid):
            fehler.append(f"{wo}: Id nur aus a-z, 0-9 und Bindestrichen, in zwei Teilen mit /")
            continue
        if vid in erklaert:
            fehler.append(f"{wo}: Id steht doppelt")
        if vid in pruefung:
            fehler.append(f"{wo}: Id gehört schon einem Prüfungsvideo")
        if belegt.get(vid, pid) != pid:
            fehler.append(f"{wo}: Id gehört schon dem Paket {belegt[vid]}")
        erklaert.add(vid)
        belegt.setdefault(vid, pid)
    return fehler, erklaert


def technik_fehler(wo, t, videos, ids):
    fehler = felder_fehler(wo, t, TECHNIK_FELDER, TECHNIK_PFLICHT)
    if not isinstance(t, dict):
        return fehler
    if "id" in t and not (isinstance(t["id"], str) and ID.fullmatch(t["id"])):
        fehler.append(f"{wo}: Id nur aus a-z, 0-9 und Bindestrichen")
    if "video" in t and t["video"] not in videos:
        fehler.append(f"{wo}: Video {t['video']} steht nicht in videos")
    if "von" in t and "bis" in t:
        if not (zahl(t["von"]) and zahl(t["bis"])):
            fehler.append(f"{wo}: von und bis sind Sekunden (Zahlen)")
        elif not 0 <= t["von"] < t["bis"]:
            fehler.append(f"{wo}: von {t['von']} bis {t['bis']}")
    wie = t.get("wie", [])
    if not isinstance(wie, list):
        return fehler + [f"{wo}: wie ist eine Liste von Ids"]
    # Doppelt nennte die App dieselbe Technik zweimal im Blatt.
    doppelt = sorted({w for w in wie if wie.count(w) > 1})
    return (fehler + [f"{wo}: wie {w}: unbekannte Id im Programm" for w in wie if w not in ids]
            + [f"{wo}: wie {w} steht doppelt" for w in doppelt])


def abschnitt_fehler(pid, d, videos, ids):
    fehler = liste_fehler(pid, d, "abschnitte")
    gesehen = set()
    for a in d.get("abschnitte") or []:
        wo = f"{pid}, Abschnitt {a.get('titel') if isinstance(a, dict) else a}"
        fehler += felder_fehler(wo, a, ABSCHNITT_FELDER, ("titel", "techniken"))
        if not isinstance(a, dict) or "techniken" not in a:
            continue
        fehler += liste_fehler(wo, a, "techniken")
        for t in a["techniken"] if isinstance(a["techniken"], list) else []:
            tid = t.get("id") if isinstance(t, dict) else None
            fehler += technik_fehler(f"{wo}, Technik {tid}", t, videos, ids)
            if tid in gesehen:
                fehler.append(f"{pid}: Technik {tid} steht doppelt")
            gesehen.add(tid)
    return fehler


def pruefe_paket(pid, d, ids, pruefung, belegt, bundles):
    """Was an einem Paket nicht stimmt. `belegt`: Videoschlüssel der bisher geprüften Pakete."""
    fehler = []
    if not ID.fullmatch(pid):
        fehler.append(f"{pid}: Id (Dateiname) nur aus a-z, 0-9 und Bindestrichen")
    if pid in bundles:
        fehler.append(f"{pid}: Id gehört schon einem Bundle aus tools/bundles.yaml")
    fehler += felder_fehler(pid, d, PAKET_FELDER, ("titel", "sparte", "videos", "abschnitte"))
    if not isinstance(d, dict):
        return fehler
    if "sparte" in d and d["sparte"] not in SPARTEN:
        fehler.append(f"{pid}: Sparte {d['sparte']}, erlaubt: {', '.join(SPARTEN)}")
    video, erklaert = video_fehler(pid, d, belegt, pruefung)
    return fehler + video + abschnitt_fehler(pid, d, erklaert, ids)


def pruefe_alle(ids, pruefung):
    """Alle Pakete gegen das Programm (`ids`) und die Prüfungsvideos (`pruefung`): die Liste der Fehler."""
    pakete, fehler = laden()
    bundles = {b["id"] for b in yaml.safe_load(BUNDLES.read_text(encoding="utf-8"))["bundles"]}
    belegt = {}
    for pid, d in pakete.items():
        fehler += pruefe_paket(pid, d, ids, pruefung, belegt, bundles)
    return fehler


def fehler_alle():
    ids, pruefung = programmdaten()
    return pruefe_alle(ids, pruefung)


def ist_entwurf(d):
    return any(t.get("pruefen") for a in d["abschnitte"] for t in a["techniken"])


# ── Inhalt ──

def mit_englisch(quelle, felder):
    """Die Felder und ihr `_en`, soweit vorhanden."""
    ziel = {}
    for f in felder:
        for name in (f, f + "_en"):
            if name in quelle:
                ziel[name] = quelle[name]
    return ziel


def inhalt(pid):
    """Der Inhalt des Pakets für das Bundle (Format 1, tools/lernpakete.md): Technik-Ids mit Vorsatz,
    Kanji (`jp`) aus dem Glossar wie im Programm."""
    d = yaml.safe_load((PAKETE / f"{pid}.yaml").read_text(encoding="utf-8"))
    sparte = d["sparte"]
    datei, bausteine = SPARTEN[sparte]
    gloss = daten.Glossar(datei, bausteine)

    def jp(name):
        return gloss.kanji(sparte, name, leise=True)

    def technik(t):
        ziel = {"id": f"{VORSATZ}{pid}/{t['id']}", **mit_englisch(t, ["name"]), "jp": jp(t["name"])}
        if "angriff" in t:
            ziel["angriff"] = {"name": t["angriff"], **({"name_en": t["angriff_en"]} if "angriff_en" in t else {}),
                               "jp": jp(t["angriff"])}
        ziel.update(mit_englisch(t, ["zusatz", "text"]))
        ziel.update({k: t[k] for k in ("wie", "video", "von", "bis") if k in t})
        return {k: v for k, v in ziel.items() if v is not None}

    def abschnitt(a):
        return {**mit_englisch(a, ["titel", "text"]), "techniken": [technik(t) for t in a["techniken"]]}

    return {"format": FORMAT, "id": pid, **mit_englisch(d, ["titel"]), "sparte": sparte,
            **mit_englisch(d, ["text"]),
            "videos": [{"id": v["id"], **mit_englisch(v, ["titel"]), **({"beschnitt": v["beschnitt"]} if "beschnitt" in v else {})}
                       for v in d["videos"]],
            "abschnitte": [abschnitt(a) for a in d["abschnitte"]]}


# ── Entwurf aus Untertiteln ──

def sekunden(m):
    stunden, minuten, s, ms = m.groups()
    return int(stunden or 0) * 3600 + int(minuten) * 60 + int(s) + int(ms) / 1000


def untertitel(text):
    """[(von, bis, Text)] aus SRT oder WebVTT. Kopfblöcke (WEBVTT, NOTE …) fallen weg, Marken wie <c> auch,
    ein Text über mehrere Zeilen wird eine Zeile."""
    zeilen = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").lstrip("﻿")):
        zeile = block.strip().splitlines()
        if not zeile or zeile[0].startswith(KOPF_BLOECKE):
            continue
        pos = next((i for i, z in enumerate(zeile) if ENDE in z), None)
        if pos is None:
            continue
        zeiten = [ZEIT.search(t) for t in zeile[pos].split(ENDE)]
        if not all(zeiten):
            continue
        inhalt_ = " ".join(MARKE.sub("", z).strip() for z in zeile[pos + 1:])
        inhalt_ = " ".join(inhalt_.split())
        if inhalt_:
            zeilen.append((sekunden(zeiten[0]), sekunden(zeiten[1]), inhalt_))
    return zeilen


def webvtt(text):
    """WebVTT-Text aus WebVTT (bleibt) oder SRT: Kommas der Zeiten werden Punkte, Nummern der Blöcke fallen weg,
    der Kopf WEBVTT kommt davor."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if text.startswith(VTT_KOPF):
        return text.rstrip("\n") + "\n"
    blocks = []
    for block in re.split(r"\n\s*\n", text.strip()):
        zeilen = block.splitlines()
        if zeilen and zeilen[0].strip().isdigit():
            zeilen = zeilen[1:]
        if not zeilen:
            continue
        zeilen[0] = ZEIT_KOMMA.sub(r"\1.\2", zeilen[0])
        blocks.append("\n".join(zeilen))
    return VTT_KOPF + "\n\n" + "\n\n".join(blocks) + "\n"


def ist_kandidat(zeile):
    if len(zeile.split()) > KANDIDAT_WOERTER or zeile[-1] in SATZENDE:
        return False
    return zeile[0].isupper() or zeile[0].isdigit()


def entwurf(zeilen, video, pid=None):
    """Der YAML-Entwurf als Text: jede Kandidatenzeile eine Technik mit `pruefen: true`."""
    kandidaten, vorher = [], None
    for von, _, text in zeilen:
        text = text.lstrip("- ").strip()
        if text and text != vorher and ist_kandidat(text):
            kandidaten.append((von, text))
        vorher = text
    ende = max((bis for _, bis, _ in zeilen), default=0)
    techniken, benutzt = [], {}
    for i, (von, text) in enumerate(kandidaten):
        bis = kandidaten[i + 1][0] if i + 1 < len(kandidaten) else ende
        tid = daten.kennung(text) or "technik"
        benutzt[tid] = benutzt.get(tid, 0) + 1
        if benutzt[tid] > 1:
            tid = f"{tid}-{benutzt[tid]}"
        techniken.append({"id": tid, "name": text, "video": video, "von": round(von, 3), "bis": round(bis, 3),
                          "pruefen": True})
    d = {"titel": pid or "…", "sparte": "aikido",
         "videos": [{"id": video, "datei": "…", "titel": "…"}],
         "abschnitte": [{"titel": ABSCHNITT_ENTWURF, "techniken": techniken}]}
    kopf = "# Entwurf aus Untertiteln: Zeiten, Namen und Sparte prüfen, dann `pruefen` löschen.\n"
    return kopf + yaml.safe_dump(d, allow_unicode=True, sort_keys=False)


# ── Aufruf ──

def befehl_pruefen(args):
    fehler = fehler_alle()
    for f in fehler:
        print(f"paket: {f}", file=sys.stderr)
    if fehler:
        sys.exit(1)
    print(f"paket: {len(laden()[0])} Pakete in Ordnung", file=sys.stderr)


def befehl_inhalt(args):
    if not (PAKETE / f"{args.id}.yaml").exists():
        sys.exit(f"paket: {args.id} gibt es nicht in {PAKETE}")
    print(json.dumps(inhalt(args.id), ensure_ascii=False, indent=1))


def befehl_entwurf(args):
    zeilen = untertitel(Path(args.untertitel).read_text(encoding="utf-8"))
    text = entwurf(zeilen, args.video, args.id)
    if "pruefen" not in text:
        print("paket: keine kurzen Zeilen gefunden, der Entwurf hat keine Techniken", file=sys.stderr)
    print(text, end="")


# ── Vorschau ──

def mmss(sek):
    sek = int(sek)
    return f"{sek // 60}:{sek % 60:02d}"


def bild_zeiten(t):
    """Drei Zeiten (Sekunden) in der Technik: von + Rand, die Mitte, bis − Rand, auf von…bis begrenzt."""
    von, bis = t["von"], t["bis"]
    roh = (von + VORSCHAU_RAND, (von + bis) / 2, bis - VORSCHAU_RAND)
    return sorted(round(min(max(z, von), bis), 3) for z in roh)


def bild_name(tid, nr, zeit):
    """Die Zeit (ms) steht im Namen: Wer die Zeiten ändert, bekommt neue Bilder, die alten fallen weg."""
    return f"{tid}-{nr}-{round(zeit * 1000)}.jpg"


def bild_holen(video, zeit, ziel):
    """Ein Standbild nach `ziel`; True, wenn es entstand. -ss vor -i springt, statt zu dekodieren."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(zeit), "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={VORSCHAU_BREITE}:-2", "-q:v", VORSCHAU_QUALITAET, str(ziel)],
                       capture_output=True, text=True)
    if r.returncode == 0 and ziel.exists():
        return True
    ziel.unlink(missing_ok=True)
    print(f"paket: kein Bild bei {zeit} s in {video}: {r.stderr.strip()}", file=sys.stderr)
    return False


def vorschau_seite(d, bilder):
    """Die index.html: je Abschnitt eine Überschrift, je Technik eine Zeile mit Angaben und ihren Bildern.
    `bilder`: {Technik-Id: [(Zeit, Dateiname oder None)]}."""
    e = html.escape
    zeilen = ["<!doctype html>", '<html lang="de"><head><meta charset="utf-8">',
              f"<title>Vorschau {e(str(d['titel']))}</title><style>{VORSCHAU_CSS}</style></head><body>",
              f"<h1>{e(str(d['titel']))}</h1>"]
    for a in d["abschnitte"]:
        zeilen.append(f"<h2>{e(str(a['titel']))}</h2>")
        for t in a["techniken"]:
            marke = ' <span class="pruefen">pruefen</span>' if t.get("pruefen") else ""
            zeilen.append(f'<div class="t"><p><b>{e(str(t["name"]))}</b>{marke}</p>')
            for feld in ("angriff", "zusatz"):
                if feld in t:
                    zeilen.append(f"<p>{feld.capitalize()}: {e(str(t[feld]))}</p>")
            zeilen.append(f"<p>{mmss(t['von'])}–{mmss(t['bis'])} ({t['von']}–{t['bis']} s)</p>")
            zeilen.append('<div class="bilder">')
            for zeit, name in bilder[t["id"]]:
                bild = f'<img src="{e(name)}" width="{VORSCHAU_BREITE}" alt="">' if name else "kein Bild"
                zeilen.append(f"<figure>{bild}<figcaption>{zeit} s</figcaption></figure>")
            zeilen.append("</div></div>")
    return "\n".join(zeilen + ["</body></html>", ""])


def vorschau(pid, videos_ordner):
    """Schreibt die Vorschau von Paket `pid` nach <GEHEIM>/arbeit/<pid>/vorschau/; gibt den Ordner zurück."""
    if not ID.fullmatch(pid):
        sys.exit(f"paket: Id {pid} nur aus a-z, 0-9 und Bindestrichen")
    d = yaml.safe_load((PAKETE / f"{pid}.yaml").read_text(encoding="utf-8"))

    # Ein Entwurf ist ungeprüft: Seine Technik-Ids werden Dateinamen und müssen im Ordner bleiben.
    falsch = [str(t.get("id")) for a in d["abschnitte"] for t in a["techniken"]
              if not (isinstance(t.get("id"), str) and ID.fullmatch(t["id"]))]
    if falsch:
        sys.exit("paket: Technik-Ids nur aus a-z, 0-9 und Bindestrichen: " + ", ".join(falsch))

    # Standbilder sind Videoinhalt: nie in ein Git-Repo, wie bei bundle.py.
    import bundle       # erst hier: bundle.py lädt selbst paket.py
    repo = bundle.repo_von(GEHEIM.resolve())
    if repo:
        sys.exit(f"paket: {GEHEIM} liegt im Git-Repo {repo}; MITORI_BUNDLE_GEHEIM außerhalb setzen")
    dateien = {v["id"]: Path(videos_ordner) / v["datei"] for v in d["videos"]}
    fehlt = [str(p) for p in dateien.values() if not p.is_file()]
    if fehlt:
        sys.exit("paket: Video nicht gefunden: " + ", ".join(fehlt))

    ziel = GEHEIM / VORSCHAU_ORDNER / pid / "vorschau"
    ziel.mkdir(parents=True, exist_ok=True)
    bilder, behalten = {}, set()
    for a in d["abschnitte"]:
        for t in a["techniken"]:
            bilder[t["id"]] = []
            for nr, zeit in enumerate(bild_zeiten(t), 1):
                name = bild_name(t["id"], nr, zeit)
                if not (ziel / name).exists() and not bild_holen(dateien[t["video"]], zeit, ziel / name):
                    name = None
                if name:
                    behalten.add(name)
                bilder[t["id"]].append((zeit, name))
    for alt in ziel.glob("*.jpg"):
        if alt.name not in behalten:
            alt.unlink()
    (ziel / "index.html").write_text(vorschau_seite(d, bilder), encoding="utf-8")
    return ziel


def befehl_vorschau(args):
    if not shutil.which("ffmpeg"):
        sys.exit("paket: ffmpeg fehlt (nötig für die Standbilder der Vorschau)")
    if not (PAKETE / f"{args.id}.yaml").exists():
        sys.exit(f"paket: {args.id} gibt es nicht in {PAKETE}")
    if args.videos is None:
        import bundle       # erst hier: bundle.py lädt selbst paket.py
        args.videos = bundle.LERNVIDEOS
    print(vorschau(args.id, args.videos) / "index.html")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="befehl")
    sub.add_parser("pruefen")
    i = sub.add_parser("inhalt")
    i.add_argument("id")
    e = sub.add_parser("entwurf")
    e.add_argument("untertitel")
    e.add_argument("--video", required=True, help="Videoschlüssel, z. B. shirakawa-1/v1")
    e.add_argument("--id", help="Id des Pakets")
    v = sub.add_parser("vorschau")
    v.add_argument("id")
    v.add_argument("--videos", help="Ordner der Lernvideos (Standard wie bundle.py)")
    args = p.parse_args()
    {"pruefen": befehl_pruefen, "inhalt": befehl_inhalt, "entwurf": befehl_entwurf,
     "vorschau": befehl_vorschau,
     None: befehl_pruefen}[args.befehl](args)


if __name__ == "__main__":
    main()
