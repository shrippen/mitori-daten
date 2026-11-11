#!/usr/bin/env python3
"""Video-Bundles für Mitori: beschneiden, verschlüsseln, Codes je DVD, Manifest, Upload.

Aufruf aus dem Projektordner:
  python3 tools/bundle.py stand                              was gebaut ist, Größen, Codes
  python3 tools/bundle.py build aikido-kyu [--videos "../Mitori Videos"] [--version 2] [--ohne-kodieren]
  python3 tools/bundle.py build aikido-kyu --videos "../Remaster" --fertig [--schnitt schnitt.yaml]
                                                             von Hand fertige Videos, nur verschlüsseln
  python3 tools/bundle.py build shirakawa-1 [--videos "../Mitori Lernvideos"]    ein Lernpaket (<PAKETE>/<id>.yaml), sonst wie ein Bundle
  python3 tools/bundle.py alle [--neu] [--videos …] [--lernvideos …] [--ohne-kodieren|--fertig] [--schnitt …]    alle Bundles und Lernpakete, Gebautes bleibt
  python3 tools/bundle.py verifizieren [aikido-kyu]          entschlüsselt alles, prüft Größe, sha256, Bilderzahl
  python3 tools/bundle.py codes aikido-kyu --anzahl 50 --fuer "Dojo Köln"   Lizenzen: CSV, Einträge im Manifest
  python3 tools/bundle.py sperren 7KQ2M-X9HDV-3TAPR-WE6YC    Eintrag eines Codes aus dem Manifest
  python3 tools/bundle.py pruefen 7KQ2M-X9HDV-3TAPR-WE6YC    öffnet den Schlüssel wie die App
  python3 tools/bundle.py hochladen --probe                  zeigt, was hochginge
  python3 tools/bundle.py hochladen --verband-stimmt-zu [--nur-manifest]   Videos zu Caddy, Manifest zu Gitea

Lernpakete (tools/paket.py, tools/lernpakete.md) sind Bundles mit eigenen Techniken: Ihre Videos stehen in
<PAKETE>/<id>.yaml (`datei` relativ zu --videos, Standard LERNVIDEOS; bei `alle` --lernvideos), werden wie Prüfungsvideos kodiert
(ohne `beschnitt` nur HEVC, kein Schnitt). Dazu kommt `inhalt.mvb`: der Inhalt des Pakets als JSON (UTF-8),
verschlüsselt wie ein Video mit dem Schlüssel des Pakets. Ein Paket mit `pruefen: true` baut `build` nicht.

Der Weg: build oder alle → verifizieren → codes → stand → hochladen. Nichts geht ohne
--verband-stimmt-zu hinaus; hochgeladen wird nur Verschlüsseltes. Mit Code lädt die App das Bundle.

Auslieferung: Die Videos liegen als statische Dateien auf dem Server (Caddy, ohne `browse`), immer nur
die aktuelle Version. Das Manifest liegt auf Gitea und nennt ihre Adressen. Reihenfolge beim Hochladen:

  neue Dateien kopieren → Adressen prüfen → Manifest ersetzen → alte Versionen löschen

Scheitert ein Schritt vor dem Manifest, gilt das alte mit seinen Dateien weiter. Gitea kann ein Paket nur
löschen und neu anlegen: Scheitert das auch nach drei Versuchen, kann das Manifest dort fehlen, bis
`hochladen --verband-stimmt-zu --nur-manifest` es nachholt. Die alten Dateien bleiben dann liegen, bis
ein voller Lauf sie löscht. Der Server braucht kurz Platz für beide Fassungen.

Geheimes (Inhaltsschlüssel, Codes, die beschnittenen Videos) liegt nie im Repo, sondern im Ordner
MITORI_BUNDLE_GEHEIM (Standard ../mitori-bundle-geheim; darin eine README.md mit der Anleitung):
  schluessel/<bundle>.key      32 Byte je Bundle, bleibt über Versionen (die Codes gelten weiter)
  codes/<bundle>.csv           Code, Datum, Kennung im Manifest, für wen (die Lizenz; für den Verband)
  aus/<bundle>/<version>/      die verschlüsselten Dateien zum Hochladen
  manifest.json                das Manifest (öffentlich: verrät weder Codes noch Schlüssel)
  gitea-token                  Token für den Upload des Manifests (Paket schreiben)
  video-basis                  Adresse des Video-Ordners: https://videos.example.org/mitori
  video-ziel                   derselbe Ordner für rsync: user@server:/srv/mitori-videos

Welche Videos ein Bundle hat: tools/bundles.yaml. Beschnitt wie in mitori-daten.json
(`beschnitt`: Schwarz oben und unten mit den eingebrannten Titeln fällt weg), HEVC hoher Qualität;
Kapitel bleiben, die Zeiten stimmen weiter. Mit --fertig bleibt die Datei, wie sie ist; sie gilt als
beschnitten. Die Schnittpunkte kommen aus daten/videos.yaml oder, wenn sich die Zeitlinie geändert
hat, aus --schnitt (dasselbe Format). Sie stehen je Datei im Manifest: Die App merkt sie sich mit der
geladenen Version, so passen sie immer zur Datei auf dem Gerät.

Formate (dieselben in app/store/bundlecrypto.cpp):

  Code      20 Zeichen Crockford-Base32 (0-9 A-Z ohne I L O U), 19 zufällig (95 Bit) und ein
            Prüfzeichen (Luhn mod 32); angezeigt in Gruppen zu fünf: 7KQ2M-X9HDV-3TAPR-WE6YC.
            Eingabe: Groß/klein, Bindestriche und Leerzeichen egal, O gilt als 0, I und L als 1.
  Kennung   hex(BLAKE2b-128("mitori-code:" + Code)): findet den Eintrag, verrät den Code nicht
  Umhüllung Argon2id(Code, Salz 16 Byte, t, m KiB, 1 Spur) → 32 Byte; damit XChaCha20-Poly1305
            über den Inhaltsschlüssel, Nonce 24 Byte, AD "mitori-key:" + Bundle-Id;
            gespeichert: base64(Nonce + Geheimtext + Tag)
  Datei     "MITORIV1" + Präfix (16 Byte), dann Blöcke zu 1 MiB Klartext (der letzte kürzer, bei
            leerer Datei ein leerer), jeder XChaCha20-Poly1305 mit Nonce = Präfix + Index (8 Byte
            LE), AD = "mitori-chunk" + Index (8 Byte LE) + 1 Byte "letzter Block"; Block =
            Geheimtext + Tag (16 Byte). Ein abgeschnittener oder umgestellter Download fällt auf.

  manifest.json
  {"format": 2,
   "bundles": [{"id": "aikido-kyu", "version": 2, "titel": "Aikido · alle Kyu", "videos": [
                  {"video": "aikido/k5", "datei": "aikido-k5.mvb", "groesse": 123, "sha256": "…",
                   "url": "https://videos.example.org/mitori/aikido-kyu/2/aikido-k5.mvb",
                   "klar": 120, "beschnitten": true, "bilder": 3000,
                   "kapitel": [{"id": "aikido/…/ikkyo-1", "von": 302.32, "bis": 343.64}]}],
                "hinweis": "neu geschnitten …"}],
   "codes": {"<Kennung>": {"bundle": "aikido-kyu", "salz": "…", "t": 3, "m": 65536, "schluessel": "…"}}}
  Lernpakete stehen unter "lernpakete" (Mitori bis 0.3.0 kennt nur "bundles" und überliest den Rest):
   "lernpakete": [{"id": "shirakawa-1", "version": 1, "titel": "…", "titel_en": "…", "videos": [
                    {"video": "shirakawa-1/v1", "datei": "shirakawa-1-v1.mvb", "groesse": 123, "sha256": "…",
                     "klar": 120, "beschnitten": true, "bilder": 3000}],
                  "inhalt": {"datei": "inhalt.mvb", "format": 1, "groesse": 456, "sha256": "…", "klar": 440},
                  "hinweis": ""}]
  Wie ein Bundle, aber ohne "kapitel" (die Stellen verraten die Techniken); "titel_en" nur, wo es abweicht.
  Codes stehen wie bei jedem Bundle unter "codes".
  Das Manifest: <GITEA>/mitori-manifest/1/manifest.json. `url` kommt erst beim Hochladen dazu
  (<video-basis>/<bundle>/<version>/<datei>), auch für `inhalt`.

Braucht PyNaCl (libsodium), PyYAML; build braucht ffmpeg.
"""
import argparse
import base64
import csv
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml
from nacl import bindings, pwhash

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paket  # noqa: E402

WURZEL = Path(__file__).resolve().parent.parent
GEHEIM = paket.GEHEIM
GITEA = "https://git.arianw.de/api/packages/shrippen/generic"
MANIFEST_FORMAT = 2
VIDEO_BASIS = "video-basis"
VIDEO_ZIEL = "video-ziel"
ORIGINALE = str(WURZEL.parent / "Mitori Videos")
LERNVIDEOS = str(WURZEL.parent / "Mitori Lernvideos")
INHALT = "inhalt.mvb"                           # der Inhalt eines Lernpakets, verschlüsselt wie ein Video
ART_VIDEO, ART_INHALT, ART_UNTERTITEL = "video", "inhalt", "untertitel"   # Art einer Datei im Bundle
UNTERTITEL_ENDUNG = ".vtt.mvb"                  # Untertitel eines Lernvideos: <video>.<sprache>.vtt.mvb
VTT_KOPF = b"WEBVTT"
MANIFEST_VERSUCHE = 3
MANIFEST_PAUSE = 10                             # Sekunden zwischen zwei Versuchen
SCHNITT_SPIEL = 1.0                             # Sekunden, die ein Schnittpunkt hinter dem Ende liegen darf
MANIFEST_PAKET = ("mitori-manifest", "1", "manifest.json")

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # Crockford-Base32
ZUFALL = 19                                     # Zeichen, dazu ein Prüfzeichen
GRUPPE = 5
MAGIE = b"MITORIV1"
PRAEFIX = 16
BLOCK = 1 << 20                                 # Klartext je Block
TAG = 16
ARGON_T = 3
ARGON_M = 64 * 1024                             # KiB


# ── Codes ──

def pruefzeichen(zeichen):
    """Luhn mod 32 über die Zeichen (Werte im Alphabet): fängt ein falsches und zwei vertauschte
    Nachbarn, außer 0 und Z (Werte 0 und 31)."""
    summe, faktor = 0, 2
    for z in reversed(zeichen):
        wert = faktor * ALPHABET.index(z)
        summe += wert // 32 + wert % 32
        faktor = 1 if faktor == 2 else 2
    return ALPHABET[(32 - summe % 32) % 32]


def normalisiert(eingabe):
    """Die 20 Zeichen eines Codes, oder None, wenn er nicht gültig ist (Länge, Zeichen, Prüfzeichen)."""
    s = eingabe.upper().replace("-", "").replace(" ", "")
    s = s.replace("O", "0").replace("I", "1").replace("L", "1")
    if len(s) != ZUFALL + 1 or any(z not in ALPHABET for z in s):
        return None
    return s if pruefzeichen(s[:-1]) == s[-1] else None


def neuer_code():
    zufall = "".join(secrets.choice(ALPHABET) for _ in range(ZUFALL))
    return zufall + pruefzeichen(zufall)


def gruppiert(code):
    return "-".join(code[i:i + GRUPPE] for i in range(0, len(code), GRUPPE))


def kennung(code):
    return hashlib.blake2b(b"mitori-code:" + code.encode("ascii"), digest_size=16).hexdigest()


def umhuellt(code, bundle, schluessel, t=ARGON_T, m=ARGON_M):
    salz = secrets.token_bytes(16)
    kek = pwhash.argon2id.kdf(32, code.encode("ascii"), salz, opslimit=t, memlimit=m * 1024)
    nonce = secrets.token_bytes(24)
    geheim = bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(schluessel, b"mitori-key:" + bundle.encode(), nonce, kek)
    return {"bundle": bundle, "salz": base64.b64encode(salz).decode(), "t": t, "m": m,
            "schluessel": base64.b64encode(nonce + geheim).decode()}


def ausgepackt(code, eintrag):
    salz = base64.b64decode(eintrag["salz"])
    kek = pwhash.argon2id.kdf(32, code.encode("ascii"), salz, opslimit=eintrag["t"], memlimit=eintrag["m"] * 1024)
    roh = base64.b64decode(eintrag["schluessel"])
    return bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(roh[24:], b"mitori-key:" + eintrag["bundle"].encode(), roh[:24], kek)


# ── Dateien ──

def _ad(index, letzter):
    return b"mitori-chunk" + struct.pack("<Q", index) + bytes([1 if letzter else 0])


def verschluesselt(quelle, ziel, schluessel):
    """Verschlüsselt quelle nach ziel; gibt (Größe, sha256 der verschlüsselten Datei, Klartextgröße)."""
    klar = os.path.getsize(quelle)
    praefix = secrets.token_bytes(PRAEFIX)
    h = hashlib.sha256()
    with open(quelle, "rb") as rein, open(ziel, "wb") as raus:
        def schreib(b):
            raus.write(b)
            h.update(b)
        schreib(MAGIE + praefix)
        index, gelesen = 0, 0
        while True:
            block = rein.read(BLOCK)
            gelesen += len(block)
            letzter = gelesen >= klar
            nonce = praefix + struct.pack("<Q", index)
            schreib(bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(block, _ad(index, letzter), nonce, schluessel))
            index += 1
            if letzter:
                break
    return os.path.getsize(ziel), h.hexdigest(), klar


def entschluesselt(quelle, ziel, schluessel):
    groesse = os.path.getsize(quelle)
    with open(quelle, "rb") as rein, open(ziel, "wb") as raus:
        kopf = rein.read(len(MAGIE) + PRAEFIX)
        if kopf[:len(MAGIE)] != MAGIE:
            raise ValueError("keine Mitori-Videodatei")
        praefix = kopf[len(MAGIE):]
        pos, index = len(kopf), 0
        while True:
            block = rein.read(BLOCK + TAG)
            pos += len(block)
            letzter = pos >= groesse
            nonce = praefix + struct.pack("<Q", index)
            raus.write(bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(block, _ad(index, letzter), nonce, schluessel))
            index += 1
            if letzter:
                break


# ── Manifest und Geheimes ──

def repo_von(pfad):
    """Das Git-Repo, in dem pfad läge, oder None."""
    for ordner in [pfad, *pfad.parents]:
        if (ordner / ".git").exists():
            return ordner
    return None


def geheim_pruefen():
    """Schlüssel, Codes und Videos kommen nie in ein Repo: der Ordner liegt daneben, nur für den Besitzer."""
    repo = repo_von(GEHEIM.resolve())
    if repo:
        sys.exit(f"bundle: {GEHEIM} liegt im Git-Repo {repo}; MITORI_BUNDLE_GEHEIM außerhalb setzen")
    GEHEIM.mkdir(parents=True, exist_ok=True)
    os.chmod(GEHEIM, 0o700)


def verschluesselt_pruefen(pfad):
    """Vor dem Upload: nur, was wirklich verschlüsselt ist, verlässt den Rechner."""
    with open(pfad, "rb") as f:
        if f.read(len(MAGIE)) != MAGIE:
            sys.exit(f"bundle: {pfad} ist nicht verschlüsselt, nichts wird hochgeladen")


def manifest_lesen():
    p = GEHEIM / "manifest.json"
    if p.exists():
        m = json.loads(p.read_text(encoding="utf-8"))
        m["format"] = MANIFEST_FORMAT   # ein älterer Stand: die Adressen kommen beim Hochladen dazu
        m.pop("basis", None)
        m.setdefault("lernpakete", [])
        return m
    return {"format": MANIFEST_FORMAT, "bundles": [], "lernpakete": [], "codes": {}}


def manifest_schreiben(m):
    geheim_pruefen()
    p = GEHEIM / "manifest.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)


def schluessel(bundle):
    geheim_pruefen()
    p = GEHEIM / "schluessel" / f"{bundle}.key"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(secrets.token_bytes(32))
        os.chmod(p, 0o600)
    return p.read_bytes()


def vorhandener_schluessel(bundle):
    """Zum Prüfen: legt nie einen an (spätere Codes umhüllten sonst einen, der die Videos nicht öffnet)."""
    p = GEHEIM / "schluessel" / f"{bundle}.key"
    return p.read_bytes() if p.exists() else None


# Ids werden Ordnernamen in der App (BundleShelf::validId): nur a-z, 0-9 und Bindestriche.
ID = paket.ID


def eintraege(m):
    """Bundles und Lernpakete des Manifests."""
    return m["bundles"] + m.get("lernpakete", [])


def ist_paket(eintrag):
    return "inhalt" in eintrag


def untertitel_von(eintrag):
    """Die Untertitel der Videos eines Eintrags im Manifest."""
    return [u for v in eintrag["videos"] for u in v.get("untertitel", [])]


def dateien_von(eintrag):
    """Die Dateien eines Eintrags im Manifest: die Videos, bei einem Lernpaket dazu Untertitel und Inhalt."""
    return eintrag["videos"] + untertitel_von(eintrag) + ([eintrag["inhalt"]] if ist_paket(eintrag) else [])


def paket_ids():
    return sorted(paket.laden()[0])


def definitionen():
    liste = yaml.safe_load((WURZEL / "tools" / "bundles.yaml").read_text(encoding="utf-8"))["bundles"]
    for b in liste:
        if not ID.fullmatch(b["id"]):
            sys.exit(f"bundles.yaml: Id „{b['id']}“ nur aus a-z, 0-9 und Bindestrichen")
    return {b["id"]: b for b in liste}


def videodaten():
    p = WURZEL / "build" / "daten" / "mitori-daten.json"
    if not p.exists():
        subprocess.run([sys.executable, str(WURZEL / "tools" / "daten.py")], check=True)
    return json.loads(p.read_text(encoding="utf-8"))["videos"]


def schnittpunkte(video, quelle=None):
    """Die Stellen der Techniken in einem Video: [{id, von, bis}], aus daten/videos.yaml oder `quelle`.
    Eine Technik mit `fehlt: true` ist nicht im Video und hat keine Stelle."""
    pfad = Path(quelle) if quelle else WURZEL / "daten" / "videos.yaml"
    alle = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    kapitel = (alle.get(video) or {}).get("kapitel", [])
    return [{"id": k["id"], "von": k["von"], "bis": k["bis"]} for k in kapitel if not k.get("fehlt")]


def schnitt_fehler(video, kapitel, laenge):
    """Was an den Schnittpunkten nicht zur Datei passt; `laenge` in Sekunden, None ohne ffprobe."""
    if not kapitel:
        return [f"{video}: keine Schnittpunkte"]
    fehler = [f"{video}: {k['id']}: von {k['von']} bis {k['bis']}" for k in kapitel if not 0 <= k["von"] < k["bis"]]
    if laenge is not None:
        fehler += [f"{video}: {k['id']} endet bei {k['bis']} s, die Datei bei {laenge:.1f} s"
                   for k in kapitel if k["bis"] > laenge + SCHNITT_SPIEL]
    return fehler


def schnitt_ids_fehler(video, kapitel):
    """Eigene Schnittpunkte müssen dieselben Techniken nennen wie die Daten. Für eine fehlende nähme die
    App die Stelle der alten Zeitlinie, eine unbekannte fände sie nie."""
    soll = {k["id"] for k in schnittpunkte(video)}
    ids = [k["id"] for k in kapitel]
    ist = set(ids)
    return ([f"{video}: {i} steht doppelt" for i in sorted({i for i in ids if ids.count(i) > 1})]
            + [f"{video}: Schnittpunkt fehlt für {i}" for i in sorted(soll - ist)]
            + [f"{video}: unbekannte Technik {i}" for i in sorted(ist - soll)])


# ── Befehle ──

MINDESTLAENGE = 0.9    # kürzer als so viel der Quelle: hält an
GANZ = 0.98            # kürzer als so viel: ein Hinweis


def laufzeit(pfad):
    """Wie lange die Videospur läuft, in Sekunden: von der ersten zur letzten Zeitmarke, nicht die Kopfdaten (dort
    die längste Spur, bei einem Rest die ganze Länge). None, wenn die Datei fehlt oder keine Marken hat."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                        "-of", "csv=p=0", str(pfad)], capture_output=True, text=True)
    zeiten = [float(z) for z in (zeile.strip().strip(",") for zeile in r.stdout.splitlines())
              if z.replace(".", "", 1).isdigit()]
    return max(zeiten) - min(zeiten) if zeiten else None


def bilder_der_kodierung(video, quelle, klar, laenge_egal=False):
    """Was `verifizieren` später wiederfinden muss, nach einem Vergleich mit der Quelle. Hält an, löscht nie."""
    ist = bilder(klar)
    if ist is None:
        return None
    if ist == 0:
        sys.exit(f"bundle: {video}: {klar} ist nicht lesbar; die Datei löschen, dann neu bauen")
    if laenge_egal or quelle == klar:
        return ist
    soll = laufzeit(quelle)
    if soll is None:
        grund = "hat keine Zeitmarken" if Path(quelle).exists() else "fehlt (Ordner eingehängt?)"
        sys.exit(f"bundle: {video}: Quelle {quelle} {grund}; prüfen, oder --laenge-egal")
    reicht = laufzeit(klar) or 0
    if reicht < soll * MINDESTLAENGE:
        sys.exit(f"bundle: {video}: {klar} läuft {reicht:.1f} s, die Quelle {soll:.1f} s; "
                 "die Datei löschen und neu bauen, oder --laenge-egal")
    if reicht < soll * GANZ:
        print(f"bundle: Achtung, {video} läuft {reicht:.1f} s, die Quelle {soll:.1f} s; bitte ansehen", file=sys.stderr)
    return ist


def beschnitten(quelle, ziel, beschnitt):
    """Neu kodiert ohne die schwarzen Balken (HEVC, hohe Qualität), Kapitel und Ton bleiben."""
    # Erst fertig unter dem Zielnamen: was dort liegt, nimmt der nächste Lauf ungeprüft als fertig.
    teil = ziel.with_name(ziel.stem + ".teil.mkv")
    filtr = f"crop=iw:{beschnitt['h']}:0:{beschnitt['y']}" if beschnitt.get("h") != beschnitt.get("hoehe") else "null"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(quelle), "-map", "0:v:0", "-map", "0:a?",
                    "-map_chapters", "0", "-vf", filtr, "-fps_mode", "passthrough", "-c:v", "libx265", "-crf", "20", "-preset", "slow",
                    "-tag:v", "hvc1", "-c:a", "copy", str(teil)], check=True)
    teil.replace(ziel)


def arbeitsname(video, beschnitt):
    """Der Beschnitt im Namen: ändert er sich in den Daten, gilt die alte Kodierung nicht mehr."""
    if not beschnitt:
        return f"{video.replace('/', '-')}.mkv"
    return f"{video.replace('/', '-')}.{beschnitt.get('h')}y{beschnitt.get('y')}.mkv"


def bilder(pfad):
    """Die Bilder der Videospur, wirklich gezählt: bei einem Rest stimmt die Länge in den Kopfdaten nicht.
    0 bei einer Datei ohne Video, None ohne ffprobe."""
    if not shutil.which("ffprobe"):
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", str(pfad)], capture_output=True, text=True)
    zeilen = [z.strip().strip(",") for z in r.stdout.splitlines() if z.strip().strip(",")]
    return int(zeilen[0]) if zeilen and zeilen[0].isdigit() else 0


def neue_version(args, alt, bundle_id):
    version = args.version or ((alt["version"] + 1) if alt else 1)
    if alt and version <= alt["version"]:     # die gleiche Nummer ersetzte auf dem Server die geltende Datei
        sys.exit(f"bundle: {bundle_id} hat schon Version {alt['version']}, eine neue braucht eine höhere")
    return version


def befehl_build(args):
    geheim_pruefen()
    fertig = getattr(args, "fertig", False)
    if args.bundle in paket_ids():
        befehl_build_paket(args)
        return
    videos_ordner = Path(args.videos or ORIGINALE)
    if fertig and videos_ordner.resolve() == Path(ORIGINALE).resolve():
        sys.exit("bundle: --fertig braucht --videos mit den gemasterten Dateien, sonst gälten die Originale als beschnitten")
    b = definitionen()[args.bundle]
    daten = videodaten()
    m = manifest_lesen()
    alt = next((x for x in m["bundles"] if x["id"] == b["id"]), None)
    version = neue_version(args, alt, b["id"])
    aus = GEHEIM / "aus" / b["id"] / str(version)
    arbeit = GEHEIM / "arbeit" / b["id"]
    aus.mkdir(parents=True, exist_ok=True)
    arbeit.mkdir(parents=True, exist_ok=True)
    k = schluessel(b["id"])
    videos = []
    for v in b["videos"]:
        info = daten[v]
        quelle = videos_ordner / info["datei"]
        datei = v.replace("/", "-") + ".mvb"
        klar = arbeit / arbeitsname(v, info["beschnitt"])
        if args.ohne_kodieren or fertig:
            klar = quelle
        elif not klar.exists():
            print(f"bundle: {v} beschneiden …", file=sys.stderr)
            beschnitten(quelle, klar, info["beschnitt"])
        zahl = bilder_der_kodierung(v, quelle, klar, getattr(args, "laenge_egal", False))
        kapitel = schnittpunkte(v, getattr(args, "schnitt", None))
        fehler = schnitt_fehler(v, kapitel, laufzeit(klar) if shutil.which("ffprobe") else None)
        fehler += schnitt_ids_fehler(v, kapitel)
        if fehler:
            sys.exit("bundle: " + "; ".join(fehler))
        groesse, sha, klargroesse = verschluesselt(klar, aus / datei, k)
        videos.append({"video": v, "datei": datei, "groesse": groesse, "sha256": sha, "klar": klargroesse,
                       "beschnitten": fertig or not args.ohne_kodieren, "bilder": zahl, "kapitel": kapitel})
    eintrag = {"id": b["id"], "version": version, "titel": b["titel"], "videos": videos, "hinweis": args.hinweis or ""}
    m["bundles"] = [x for x in m["bundles"] if x["id"] != b["id"]] + [eintrag]
    m["bundles"].sort(key=lambda x: list(definitionen()).index(x["id"]))
    manifest_schreiben(m)
    print(f"bundle: {b['id']} Version {version}, {len(videos)} Dateien → {aus}", file=sys.stderr)


def paket_kodiert(v, quelle, arbeit, args):
    """Die Datei, die verschlüsselt wird: das Original (Test, fertig) oder die Kodierung, nur HEVC ohne Schnitt,
    wenn das Video keinen `beschnitt` hat."""
    if args.ohne_kodieren or getattr(args, "fertig", False):
        return quelle
    klar = arbeit / arbeitsname(v["id"], v.get("beschnitt") or {})
    if not klar.exists():
        print(f"bundle: {v['id']} kodieren …", file=sys.stderr)
        beschnitten(quelle, klar, v.get("beschnitt") or {})
    return klar


def paket_schnitt_fehler(p, video, laenge):
    """Die Techniken eines Videos gegen seine Länge (die Zeiten selbst prüft tools/paket.py)."""
    stellen = [{"id": t["id"], "von": t["von"], "bis": t["bis"]}
               for a in p["abschnitte"] for t in a["techniken"] if t["video"] == video]
    return schnitt_fehler(video, stellen, laenge) if stellen else []


def paket_untertitel(v, videos_ordner, arbeit, aus, k):
    """Die Untertitel eines Videos als WebVTT verschlüsselt (Manifest-Einträge); die Klardatei bleibt nicht liegen."""
    eintraege_ = []
    for u in v.get("untertitel", []):
        quelle = videos_ordner / u["datei"]
        if not quelle.is_file():
            sys.exit(f"bundle: Untertitel {quelle} fehlt")
        datei = f"{v['id'].replace('/', '-')}.{u['sprache']}{UNTERTITEL_ENDUNG}"
        klar = arbeit / (datei + ".klar")
        klar.write_text(paket.webvtt(quelle.read_text(encoding="utf-8")), encoding="utf-8")
        try:
            groesse, sha, klargroesse = verschluesselt(klar, aus / datei, k)
        finally:
            klar.unlink(missing_ok=True)
        eintraege_.append({"sprache": u["sprache"], "datei": datei, "groesse": groesse, "sha256": sha,
                           "klar": klargroesse})
    return eintraege_


def befehl_build_paket(args):
    """Ein Lernpaket: die Videos wie die Prüfungsvideos, dazu sein Inhalt verschlüsselt als inhalt.mvb."""
    pid = args.bundle
    fehler = paket.fehler_alle()
    if fehler:
        sys.exit("bundle: " + "; ".join(fehler))
    p = paket.laden()[0][pid]
    if paket.ist_entwurf(p):
        sys.exit(f"bundle: {pid} ist ein Entwurf (pruefen: true in {paket.PAKETE / pid}.yaml), nichts wird gebaut")
    fertig = getattr(args, "fertig", False)
    videos_ordner = Path(args.videos or LERNVIDEOS)
    if fertig and videos_ordner.resolve() == Path(LERNVIDEOS).resolve():
        sys.exit("bundle: --fertig braucht --videos mit den fertig kodierten Dateien, sonst gälten die Originale als kodiert")
    m = manifest_lesen()
    alt = next((x for x in m["lernpakete"] if x["id"] == pid), None)
    version = neue_version(args, alt, pid)
    aus = GEHEIM / "aus" / pid / str(version)
    arbeit = GEHEIM / "arbeit" / pid
    aus.mkdir(parents=True, exist_ok=True)
    arbeit.mkdir(parents=True, exist_ok=True)
    k = schluessel(pid)
    videos = []
    for v in p["videos"]:
        quelle = videos_ordner / v["datei"]
        datei = v["id"].replace("/", "-") + ".mvb"
        klar = paket_kodiert(v, quelle, arbeit, args)
        zahl = bilder_der_kodierung(v["id"], quelle, klar, getattr(args, "laenge_egal", False))
        fehler = paket_schnitt_fehler(p, v["id"], laufzeit(klar) if shutil.which("ffprobe") else None)
        if fehler:
            sys.exit("bundle: " + "; ".join(fehler))
        groesse, sha, klargroesse = verschluesselt(klar, aus / datei, k)
        videos.append({"video": v["id"], "datei": datei, "groesse": groesse, "sha256": sha, "klar": klargroesse,
                       "beschnitten": fertig or not args.ohne_kodieren, "bilder": zahl})
        untertitel = paket_untertitel(v, videos_ordner, arbeit, aus, k)
        if untertitel:
            videos[-1]["untertitel"] = untertitel
    json_datei = arbeit / "inhalt.json"
    json_datei.write_text(json.dumps(paket.inhalt(pid), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    groesse, sha, klargroesse = verschluesselt(json_datei, aus / INHALT, k)
    json_datei.unlink()
    eintrag = {"id": pid, "version": version, "titel": p["titel"],
               **({"titel_en": p["titel_en"]} if "titel_en" in p else {}), "videos": videos,
               "inhalt": {"datei": INHALT, "format": paket.FORMAT, "groesse": groesse, "sha256": sha,
                          "klar": klargroesse},
               "hinweis": args.hinweis or ""}
    m["lernpakete"] = sorted([x for x in m["lernpakete"] if x["id"] != pid] + [eintrag], key=lambda x: x["id"])
    manifest_schreiben(m)
    print(f"bundle: {pid} Version {version}, {len(videos)} Videos und Inhalt → {aus}", file=sys.stderr)


def befehl_alle(args):
    """Alle Bundles nacheinander; Gebautes bleibt (ein abgebrochener Lauf geht weiter), --neu baut neu."""
    # Ein Testbau (Originale, --ohne-kodieren) zählt für den echten Lauf nicht.
    # Ein Bau ohne Schnittpunkte auch nicht: `hochladen` nähme ihn nicht.
    gebaut = {x["id"] for x in eintraege(manifest_lesen()) if (args.ohne_kodieren or not ist_testbau(x))
              and (ist_paket(x) or all(v.get("kapitel") for v in x["videos"]))}
    args.version = None
    videos, lernvideos = getattr(args, "videos", None), getattr(args, "lernvideos", None)
    pakete = paket.laden()[0]
    for bundle_id in [*definitionen(), *pakete]:
        if bundle_id in gebaut and not args.neu:
            print(f"bundle: {bundle_id} schon gebaut", file=sys.stderr)
            continue
        if bundle_id in pakete and paket.ist_entwurf(pakete[bundle_id]):
            print(f"bundle: {bundle_id} ist ein Entwurf, übersprungen", file=sys.stderr)
            continue
        args.bundle = bundle_id
        args.videos = lernvideos if bundle_id in pakete else videos     # je Art ihr Ordner
        befehl_build(args)


def ist_testbau(eintrag):
    return not all(v.get("beschnitten") for v in eintrag["videos"])


def verifiziert(bundle_id):
    """Was an einem gebauten Bundle nicht stimmt: je Datei Größe, sha256, jeder Block entschlüsselt, wie die App."""
    geheim_pruefen()
    m = manifest_lesen()
    eintrag = next((x for x in eintraege(m) if x["id"] == bundle_id), None)
    if not eintrag:
        return [f"{bundle_id}: nicht gebaut"]
    k = vorhandener_schluessel(bundle_id)
    if k is None:
        return [f"{bundle_id}: Schlüssel fehlt"]
    fehler = []
    for v in eintrag["videos"]:
        pfad = GEHEIM / "aus" / bundle_id / str(eintrag["version"]) / v["datei"]
        if not pfad.exists():
            fehler.append(f"{bundle_id}/{v['datei']}: fehlt")
            continue
        fehler += _datei_fehler(bundle_id, v, pfad, k)
    for u in untertitel_von(eintrag):
        pfad = GEHEIM / "aus" / bundle_id / str(eintrag["version"]) / u["datei"]
        fehler += _datei_fehler(bundle_id, u, pfad, k, art=ART_UNTERTITEL) if pfad.exists() \
            else [f"{bundle_id}/{u['datei']}: fehlt"]
    if ist_paket(eintrag):
        pfad = GEHEIM / "aus" / bundle_id / str(eintrag["version"]) / eintrag["inhalt"]["datei"]
        fehler += _datei_fehler(bundle_id, eintrag["inhalt"], pfad, k, art=ART_INHALT) if pfad.exists() \
            else [f"{bundle_id}/{eintrag['inhalt']['datei']}: fehlt"]
    return fehler


def _inhalt_fehler(name, probe, bundle_id):
    """Der Inhalt eines Lernpakets: JSON, zum Paket gehörig."""
    try:
        j = json.loads(probe.read_text(encoding="utf-8"))
    except ValueError:
        return [f"{name}: kein JSON"]
    if not isinstance(j, dict) or j.get("id") != bundle_id:
        return [f"{name}: gehört nicht zu {bundle_id}"]
    return []


def _untertitel_fehler(name, probe):
    """Ein Untertitel: WebVTT-Text."""
    try:
        kopf = probe.read_bytes()[:len(VTT_KOPF)]
    except OSError:
        return [f"{name}: nicht lesbar"]
    return [] if kopf == VTT_KOPF else [f"{name}: kein WebVTT"]


def _datei_fehler(bundle_id, v, pfad, k, art=ART_VIDEO):
    name = f"{bundle_id}/{v['datei']}"
    if pfad.stat().st_size != v["groesse"]:
        return [f"{name}: Größe {pfad.stat().st_size}, im Manifest {v['groesse']}"]
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for stueck in iter(lambda: f.read(BLOCK), b""):
            h.update(stueck)
    if h.hexdigest() != v["sha256"]:
        return [f"{name}: sha256 stimmt nicht"]
    probe = GEHEIM / "arbeit" / f"probe-{os.getpid()}"
    probe.parent.mkdir(parents=True, exist_ok=True)
    try:
        entschluesselt(pfad, probe, k)
        if probe.stat().st_size != v["klar"]:
            return [f"{name}: Klartext {probe.stat().st_size}, im Manifest {v['klar']}"]
        if art == ART_INHALT:
            return _inhalt_fehler(name, probe, bundle_id)
        if art == ART_UNTERTITEL:
            return _untertitel_fehler(name, probe)
        return _laenge_fehler(name, probe, v.get("bilder"))
    except Exception as e:
        return [f"{name}: lässt sich nicht entschlüsseln ({type(e).__name__})"]
    finally:
        probe.unlink(missing_ok=True)


def _laenge_fehler(name, probe, soll):
    """Spielbar und ganz? Dieselben Bilder wie beim Bauen gezählt (ffprobe, wo vorhanden)."""
    ist = bilder(probe)
    if ist is None:
        return []
    if ist == 0:
        return [f"{name}: kein spielbares Video"]
    if soll and ist != soll:
        return [f"{name}: {ist} Bilder, beim Bauen {soll}"]
    return []


def befehl_verifizieren(args):
    ids = [args.bundle] if args.bundle else [x["id"] for x in eintraege(manifest_lesen())]
    if not ids:
        sys.exit(f"bundle: keine Bundles in {GEHEIM}")
    fehler = [f for i in ids for f in verifiziert(i)]
    for f in fehler:
        print(f"bundle: {f}", file=sys.stderr)
    if fehler:
        sys.exit(1)
    print(f"bundle: {len(ids)} Bundles in Ordnung", file=sys.stderr)


def stand_zeilen():
    """Je Bundle eine Zeile: gebaut oder nicht, Version, Dateien, Größe, ausgegebene Codes."""
    m = manifest_lesen()
    codes = {}
    for c in m["codes"].values():
        codes[c["bundle"]] = codes.get(c["bundle"], 0) + 1
    gebaut = {x["id"]: x for x in eintraege(m)}
    zeilen = []
    for bundle_id in [*definitionen(), *paket_ids()]:
        x = gebaut.get(bundle_id)
        if not x:
            zeilen.append(f"{bundle_id}: nicht gebaut")
            continue
        mib = sum(v["groesse"] for v in x["videos"]) / (1 << 20)
        test = ", Testbau (unbeschnitten)" if ist_testbau(x) else ""
        zeilen.append(f"{bundle_id}: Version {x['version']}, {len(x['videos'])} Dateien, {mib:.0f} MiB, "
                      f"{codes.get(bundle_id, 0)} Codes{test}")
    return zeilen


def befehl_stand(args):
    print("\n".join(stand_zeilen()))


def befehl_codes(args):
    if args.bundle not in definitionen() and args.bundle not in paket_ids():
        sys.exit(f"bundle: unbekanntes Bundle {args.bundle}")
    m = manifest_lesen()
    k = schluessel(args.bundle)
    fuer = getattr(args, "fuer", "") or ""
    datei = GEHEIM / "codes" / f"{args.bundle}.csv"
    datei.parent.mkdir(parents=True, exist_ok=True)
    neu = not datei.exists()
    with open(datei, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if neu:
            w.writerow(["code", "datum", "kennung", "fuer"])
        for _ in range(args.anzahl):
            code = neuer_code()
            m["codes"][kennung(code)] = umhuellt(code, args.bundle, k)
            w.writerow([gruppiert(code), datetime.date.today().isoformat(), kennung(code), fuer])
    os.chmod(datei, 0o600)
    manifest_schreiben(m)
    print(f"bundle: {args.anzahl} Codes für {args.bundle} → {datei}", file=sys.stderr)


def befehl_sperren(args):
    code = normalisiert(args.code)
    if not code:
        sys.exit("bundle: kein gültiger Code")
    m = manifest_lesen()
    if m["codes"].pop(kennung(code), None) is None:
        sys.exit("bundle: Code steht nicht im Manifest")
    manifest_schreiben(m)
    print("bundle: gesperrt (nach dem Hochladen des Manifests wirksam)", file=sys.stderr)


def befehl_pruefen(args):
    code = normalisiert(args.code)
    if not code:
        sys.exit("bundle: kein gültiger Code (Länge, Zeichen oder Prüfzeichen)")
    eintrag = manifest_lesen()["codes"].get(kennung(code))
    if not eintrag:
        sys.exit("bundle: Code steht nicht im Manifest")
    k = vorhandener_schluessel(eintrag["bundle"])
    if k is None:
        sys.exit(f"bundle: Schlüssel von {eintrag['bundle']} fehlt")
    ok = ausgepackt(code, eintrag) == k
    print(f"bundle: {gruppiert(code)} öffnet {eintrag['bundle']}: {'ja' if ok else 'NEIN'}")


def hochladen(paket, version, name, daten, token, laenge=None):
    """Nach Gitea. daten: bytes oder eine offene Datei."""
    url = f"{GITEA}/{paket}/{version}/{name}"
    kopf = {"Authorization": f"token {token}"}
    try:   # eine Datei gleichen Namens zuerst löschen (das Manifest wird ersetzt)
        urllib.request.urlopen(urllib.request.Request(url, method="DELETE", headers=kopf), timeout=60)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    if laenge is not None:
        kopf["Content-Length"] = str(laenge)
    # Ohne Angabe schickt urllib application/x-www-form-urlencoded, Gitea antwortet darauf mit 500.
    kopf["Content-Type"] = "application/octet-stream"
    urllib.request.urlopen(urllib.request.Request(url, data=daten, method="PUT", headers=kopf), timeout=3600)
    print(f"bundle: hochgeladen {url}", file=sys.stderr)


def einstellung(name):
    p = GEHEIM / name
    if not p.exists():
        sys.exit(f"bundle: {p} fehlt (siehe tools/bundle.py), nichts wird hochgeladen")
    return p.read_text(encoding="utf-8").strip().rstrip("/")


def video_url(basis, bundle, datei):
    return f"{basis}/{bundle['id']}/{bundle['version']}/{datei}"


def videos_kopieren(b, ziel, aufraeumen=False):
    """rsync nur der Dateien aus dem Manifest, nichts anderes aus dem Ordner. Mit `aufraeumen` verschwinden
    auf dem Server die anderen Versionen des Bundles."""
    filter_ = [f"--filter=+ /{b['version']}/"] + [f"--filter=+ /{b['version']}/{v['datei']}" for v in dateien_von(b)]
    aufruf = ["rsync", "-a", "--partial", "--chmod=D755,F644", *filter_, "--filter=- *"]
    if aufraeumen:
        aufruf += ["--delete", "--delete-excluded"]
    aufruf += [f"{GEHEIM / 'aus' / b['id']}/", f"{ziel}/{b['id']}/"]
    if subprocess.run(aufruf).returncode == 0:
        return
    if aufraeumen:
        sys.exit(f"bundle: Das neue Manifest gilt, aber alte Versionen ab {b['id']} bleiben liegen; ein voller Lauf löscht sie")
    sys.exit(f"bundle: rsync von {b['id']} ist gescheitert; das Manifest bleibt, wie es ist")


def adressen_fehler(m, basis):
    """Liefert der Server jede Datei des Manifests in der richtigen Größe? Vor dem Ersetzen des Manifests."""
    fehler = []
    for b in eintraege(m):
        for v in dateien_von(b):
            url = video_url(basis, b, v["datei"])
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as r:
                    laenge = r.headers.get("Content-Length")
            except (urllib.error.URLError, OSError) as e:
                fehler.append(f"{url}: {e}")
                continue
            if laenge != str(v["groesse"]):
                fehler.append(f"{url}: {laenge} Byte, im Manifest {v['groesse']}")
    return fehler


def veroeffentlichtes_manifest(m, basis):
    """Das Manifest für den Server: mit der Adresse jeder Datei."""
    aus = json.loads(json.dumps(m))
    for b in eintraege(aus):
        for v in dateien_von(b):
            v["url"] = video_url(basis, b, v["datei"])
    return aus


def manifest_ersetzen(daten, token):
    """Mit Wiederholung: Nach dem DELETE in `hochladen` fehlt es sonst auf Gitea."""
    for versuch in range(1, MANIFEST_VERSUCHE + 1):
        try:
            hochladen(*MANIFEST_PAKET, daten, token)
            return
        except OSError as e:     # auch URLError, HTTPError
            print(f"bundle: Manifest, Versuch {versuch}: {e}", file=sys.stderr)
            if versuch < MANIFEST_VERSUCHE:
                time.sleep(MANIFEST_PAUSE)
    sys.exit("bundle: Das Manifest ging nicht hinaus und kann auf Gitea fehlen. Nachholen mit "
             "`hochladen --verband-stimmt-zu --nur-manifest`; die alten Videos bleiben bis zum nächsten vollen Lauf.")


def befehl_hochladen(args):
    m = manifest_lesen()
    dateien = [] if args.nur_manifest else [
        (b, v["datei"], GEHEIM / "aus" / b["id"] / str(b["version"]) / v["datei"])
        for b in eintraege(m) for v in dateien_von(b)]
    if args.probe:
        p = GEHEIM / VIDEO_BASIS
        basis = einstellung(VIDEO_BASIS) if p.exists() else "<video-basis fehlt>"
        for b, name, pfad in dateien:
            groesse = f"{pfad.stat().st_size / (1 << 20):.0f} MiB" if pfad.exists() else "FEHLT"
            print(f"{video_url(basis, b, name)}  {groesse}")
        print(f"{GITEA}/{'/'.join(MANIFEST_PAKET[:2])}/{MANIFEST_PAKET[2]}")
        return
    if not args.verband_stimmt_zu:
        sys.exit("bundle: hochladen nur mit --verband-stimmt-zu (die Zustimmung des Verbands liegt vor)")
    # Alles vor dem ersten Request: was hier scheitert, hat den Rechner nicht verlassen.
    for b in eintraege(m):
        if ist_testbau(b):
            sys.exit(f"bundle: {b['id']} ist ein Testbau (unbeschnittene Originale), nichts wird hochgeladen")
    for _, _, pfad in dateien:
        if pfad.exists():
            verschluesselt_pruefen(pfad)
    if not eintraege(m):     # ein leeres Manifest nähme auf dem Server alle Codes und Bundles weg
        sys.exit(f"bundle: keine Bundles in {GEHEIM}, nichts wird hochgeladen")
    # Die Techniken nur für neue Dateien: Das Manifest allein (eine Sperre) darf nicht am Datenstand hängen.
    fehler = [f for b in m["bundles"] for v in b["videos"]
              for f in schnitt_fehler(v["video"], v.get("kapitel"), None)
              + ([] if args.nur_manifest else schnitt_ids_fehler(v["video"], v.get("kapitel") or []))]
    if fehler:
        sys.exit("bundle: " + "; ".join(fehler) + "; neu bauen, nichts wird hochgeladen")
    if not args.nur_manifest:
        if not shutil.which("ffprobe"):
            sys.exit("bundle: ohne ffprobe keine Prüfung der Videos, nichts wird hochgeladen")
        if not shutil.which("rsync"):
            sys.exit("bundle: ohne rsync gehen die Videos nicht hinaus, nichts wird hochgeladen")
        fehler = [f for b in eintraege(m) for f in verifiziert(b["id"])]
        if fehler:
            sys.exit("bundle: " + "; ".join(fehler) + "; nichts wird hochgeladen")
    basis = einstellung(VIDEO_BASIS)
    ziel = None if args.nur_manifest else einstellung(VIDEO_ZIEL)
    token = (GEHEIM / "gitea-token").read_text().strip()

    if not args.nur_manifest:
        for b in eintraege(m):
            videos_kopieren(b, ziel)
    # Auch bei --nur-manifest: Es darf keine Datei nennen, die der Server nicht hat.
    fehler = adressen_fehler(m, basis)
    if fehler:
        sys.exit("bundle: " + "; ".join(fehler) + "; das Manifest bleibt, wie es ist")
    daten = json.dumps(veroeffentlichtes_manifest(m, basis), ensure_ascii=False, indent=1).encode()
    manifest_ersetzen(daten, token)
    if not args.nur_manifest:
        for b in eintraege(m):
            videos_kopieren(b, ziel, aufraeumen=True)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="befehl", required=True)
    b = sub.add_parser("build")
    b.add_argument("bundle")
    b.add_argument("--videos", help=f"Ordner der Videos (Standard {ORIGINALE}, bei einem Lernpaket {LERNVIDEOS})")
    b.add_argument("--version", type=int)
    b.add_argument("--hinweis", help="was die neue Version bringt (Update-Hinweis in der App)")
    art = b.add_mutually_exclusive_group()
    art.add_argument("--ohne-kodieren", action="store_true", help="Originale verschlüsseln (Test)")
    art.add_argument("--fertig", action="store_true", help="von Hand fertige, beschnittene Videos nur verschlüsseln")
    b.add_argument("--schnitt", help="Schnittpunkte im Format von daten/videos.yaml")
    b.add_argument("--laenge-egal", action="store_true", help="auch eine viel kürzere Kodierung nehmen")
    c = sub.add_parser("codes")
    c.add_argument("bundle")
    c.add_argument("--anzahl", type=int, default=1)
    c.add_argument("--fuer", default="", help="wer die Codes bekommt (nur in der privaten CSV)")
    for name in ("sperren", "pruefen"):
        s = sub.add_parser(name)
        s.add_argument("code")
    h = sub.add_parser("hochladen")
    h.add_argument("--nur-manifest", action="store_true")
    h.add_argument("--probe", action="store_true", help="nur zeigen, was hochginge")
    h.add_argument("--verband-stimmt-zu", action="store_true", help="die Zustimmung liegt vor")
    a = sub.add_parser("alle")
    a.add_argument("--neu", action="store_true", help="auch schon Gebautes neu bauen")
    a.add_argument("--videos", help=f"Ordner der Prüfungsvideos (Standard {ORIGINALE})")
    a.add_argument("--lernvideos", help=f"Ordner der Lernvideos (Standard {LERNVIDEOS})")
    a.add_argument("--hinweis")
    art = a.add_mutually_exclusive_group()
    art.add_argument("--ohne-kodieren", action="store_true")
    art.add_argument("--fertig", action="store_true")
    a.add_argument("--schnitt")
    a.add_argument("--laenge-egal", action="store_true")
    r = sub.add_parser("verifizieren")
    r.add_argument("bundle", nargs="?")
    sub.add_parser("stand")
    args = p.parse_args()
    {"build": befehl_build, "codes": befehl_codes, "sperren": befehl_sperren, "pruefen": befehl_pruefen,
     "hochladen": befehl_hochladen, "alle": befehl_alle, "verifizieren": befehl_verifizieren,
     "stand": befehl_stand}[args.befehl](args)


if __name__ == "__main__":
    main()
