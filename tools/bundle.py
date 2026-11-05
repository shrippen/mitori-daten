#!/usr/bin/env python3
"""Video-Bundles für Mitori: beschneiden, verschlüsseln, Codes je DVD, Manifest, Upload.

Aufruf aus dem Projektordner:
  python3 tools/bundle.py stand                              was gebaut ist, Größen, Codes
  python3 tools/bundle.py build aikido-kyu [--videos "../Mitori Videos"] [--version 2] [--ohne-kodieren]
  python3 tools/bundle.py alle [--neu] [--videos …] [--ohne-kodieren]    alle Bundles, Gebautes bleibt
  python3 tools/bundle.py verifizieren [aikido-kyu]          entschlüsselt alles, prüft Größe, sha256, Bilderzahl
  python3 tools/bundle.py codes aikido-kyu --anzahl 50 --fuer "Dojo Köln"   Lizenzen: CSV, Einträge im Manifest
  python3 tools/bundle.py sperren 7KQ2M-X9HDV-3TAPR-WE6YC    Eintrag eines Codes aus dem Manifest
  python3 tools/bundle.py pruefen 7KQ2M-X9HDV-3TAPR-WE6YC    öffnet den Schlüssel wie die App
  python3 tools/bundle.py hochladen --probe                  zeigt, was hochginge
  python3 tools/bundle.py hochladen --verband-stimmt-zu [--nur-manifest]   als generische Pakete nach Gitea

Der Weg: build oder alle → verifizieren → codes → stand → hochladen. Nichts geht ohne
--verband-stimmt-zu hinaus; hochgeladen wird nur Verschlüsseltes. Mit Code lädt die App das Bundle.

Geheimes (Inhaltsschlüssel, Codes, die beschnittenen Videos) liegt nie im Repo, sondern im Ordner
MITORI_BUNDLE_GEHEIM (Standard ../bundle-geheim):
  schluessel/<bundle>.key      32 Byte je Bundle, bleibt über Versionen (die Codes gelten weiter)
  codes/<bundle>.csv           Code, Datum, Kennung im Manifest, für wen (die Lizenz; für den Verband)
  aus/<bundle>/<version>/      die verschlüsselten Dateien zum Hochladen
  manifest.json                das Manifest (öffentlich: verrät weder Codes noch Schlüssel)
  gitea-token                  Token für den Upload (Paket schreiben)

Welche Videos ein Bundle hat: tools/bundles.yaml. Beschnitt wie in mitori-daten.json
(`beschnitt`: Schwarz oben und unten mit den eingebrannten Titeln fällt weg), HEVC hoher Qualität;
Kapitel bleiben, die Zeiten stimmen weiter.

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
  {"format": 1,
   "bundles": [{"id": "aikido-kyu", "version": 2, "titel": "Aikido · alle Kyu", "videos": [
                  {"video": "aikido/k5", "datei": "aikido-k5.mvb", "groesse": 123, "sha256": "…",
                   "klar": 120, "beschnitten": true, "bilder": 3000}], "hinweis": "neu geschnitten …"}],
   "basis": "https://git.arianw.de/api/packages/shrippen/generic",
   "codes": {"<Kennung>": {"bundle": "aikido-kyu", "salz": "…", "t": 3, "m": 65536, "schluessel": "…"}}}
  Datei-URL: <basis>/mitori-<bundle>/<version>/<datei>; das Manifest: <basis>/mitori-manifest/1/manifest.json

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
import urllib.error
import urllib.request
from pathlib import Path

import yaml
from nacl import bindings, pwhash

WURZEL = Path(__file__).resolve().parent.parent
GEHEIM = Path(os.environ.get("MITORI_BUNDLE_GEHEIM", WURZEL.parent / "bundle-geheim"))
BASIS = "https://git.arianw.de/api/packages/shrippen/generic"
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
        return json.loads(p.read_text(encoding="utf-8"))
    return {"format": 1, "bundles": [], "basis": BASIS, "codes": {}}


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
ID = re.compile(r"[a-z0-9][a-z0-9-]*")


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


# ── Befehle ──

BILDER_SPIEL = 2    # so viele Bilder Unterschied zur Quelle sind keinen Hinweis wert


def bilder_der_kodierung(video, quelle, klar):
    """Was `verifizieren` später wiederfinden muss. Die Quelle nur als Hinweis: ihre Pakete sind nicht ihre
    Bilder (ein per Stream-Copy geschnittenes mp4 hat Vorlauf), und was hier liegt, ist fertig kodiert."""
    soll = bilder(quelle)
    ist = bilder(klar)
    if soll and ist is not None and abs(ist - soll) > BILDER_SPIEL:
        print(f"bundle: Achtung, {video} hat {ist} Bilder, die Quelle {soll} Pakete; bitte ansehen", file=sys.stderr)
    return ist


def beschnitten(quelle, ziel, beschnitt):
    """Neu kodiert ohne die schwarzen Balken (HEVC, hohe Qualität), Kapitel und Ton bleiben."""
    # Erst fertig unter dem Zielnamen: was dort liegt, nimmt der nächste Lauf ungeprüft als fertig.
    teil = ziel.with_name(ziel.stem + ".teil.mkv")
    filtr = f"crop=iw:{beschnitt['h']}:0:{beschnitt['y']}" if beschnitt.get("h") != beschnitt.get("hoehe") else "null"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(quelle), "-map", "0:v:0", "-map", "0:a?",
                    "-map_chapters", "0", "-vf", filtr, "-c:v", "libx265", "-crf", "20", "-preset", "slow",
                    "-tag:v", "hvc1", "-c:a", "copy", str(teil)], check=True)
    teil.replace(ziel)


def arbeitsname(video, beschnitt):
    """Der Beschnitt im Namen: ändert er sich in den Daten, gilt die alte Kodierung nicht mehr."""
    return f"{video.replace('/', '-')}.{beschnitt.get('h')}y{beschnitt.get('y')}.mkv"


def bilder(pfad):
    """Die Bilder der Videospur, wirklich gezählt: bei einem Rest stimmt die Länge in den Kopfdaten nicht.
    0 bei einer Datei ohne Video, None ohne ffprobe."""
    if not shutil.which("ffprobe"):
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", str(pfad)], capture_output=True, text=True)
    zahl = r.stdout.strip().strip(",")
    return int(zahl) if zahl.isdigit() else 0


def befehl_build(args):
    geheim_pruefen()
    b = definitionen()[args.bundle]
    daten = videodaten()
    m = manifest_lesen()
    alt = next((x for x in m["bundles"] if x["id"] == b["id"]), None)
    version = args.version or ((alt["version"] + 1) if alt else 1)
    aus = GEHEIM / "aus" / b["id"] / str(version)
    arbeit = GEHEIM / "arbeit" / b["id"]
    aus.mkdir(parents=True, exist_ok=True)
    arbeit.mkdir(parents=True, exist_ok=True)
    k = schluessel(b["id"])
    videos = []
    for v in b["videos"]:
        info = daten[v]
        quelle = Path(args.videos) / info["datei"]
        datei = v.replace("/", "-") + ".mvb"
        klar = arbeit / arbeitsname(v, info["beschnitt"])
        if args.ohne_kodieren:
            klar = quelle
        elif not klar.exists():
            print(f"bundle: {v} beschneiden …", file=sys.stderr)
            beschnitten(quelle, klar, info["beschnitt"])
        zahl = bilder_der_kodierung(v, quelle, klar)
        groesse, sha, klargroesse = verschluesselt(klar, aus / datei, k)
        videos.append({"video": v, "datei": datei, "groesse": groesse, "sha256": sha, "klar": klargroesse,
                       "beschnitten": not args.ohne_kodieren, "bilder": zahl})
    eintrag = {"id": b["id"], "version": version, "titel": b["titel"], "videos": videos, "hinweis": args.hinweis or ""}
    m["bundles"] = [x for x in m["bundles"] if x["id"] != b["id"]] + [eintrag]
    m["bundles"].sort(key=lambda x: list(definitionen()).index(x["id"]))
    manifest_schreiben(m)
    print(f"bundle: {b['id']} Version {version}, {len(videos)} Dateien → {aus}", file=sys.stderr)


def befehl_alle(args):
    """Alle Bundles nacheinander; Gebautes bleibt (ein abgebrochener Lauf geht weiter), --neu baut neu."""
    # Ein Testbau (Originale, --ohne-kodieren) zählt für den echten Lauf nicht.
    gebaut = {x["id"] for x in manifest_lesen()["bundles"] if args.ohne_kodieren or not ist_testbau(x)}
    args.version = None
    for bundle_id in definitionen():
        if bundle_id in gebaut and not args.neu:
            print(f"bundle: {bundle_id} schon gebaut", file=sys.stderr)
            continue
        args.bundle = bundle_id
        befehl_build(args)


def ist_testbau(eintrag):
    return not all(v.get("beschnitten") for v in eintrag["videos"])


def verifiziert(bundle_id):
    """Was an einem gebauten Bundle nicht stimmt: je Datei Größe, sha256, jeder Block entschlüsselt, wie die App."""
    geheim_pruefen()
    m = manifest_lesen()
    eintrag = next((x for x in m["bundles"] if x["id"] == bundle_id), None)
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
    return fehler


def _datei_fehler(bundle_id, v, pfad, k):
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
    ids = [args.bundle] if args.bundle else [x["id"] for x in manifest_lesen()["bundles"]]
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
    gebaut = {x["id"]: x for x in m["bundles"]}
    zeilen = []
    for bundle_id in definitionen():
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
    if args.bundle not in definitionen():
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
    """daten: bytes oder eine offene Datei (ein Video kommt nicht in den Speicher)."""
    url = f"{BASIS}/{paket}/{version}/{name}"
    kopf = {"Authorization": f"token {token}"}
    try:   # eine Datei gleichen Namens zuerst löschen (das Manifest wird ersetzt)
        urllib.request.urlopen(urllib.request.Request(url, method="DELETE", headers=kopf), timeout=60)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    if laenge is not None:
        kopf["Content-Length"] = str(laenge)
    urllib.request.urlopen(urllib.request.Request(url, data=daten, method="PUT", headers=kopf), timeout=3600)
    print(f"bundle: hochgeladen {url}", file=sys.stderr)


def befehl_hochladen(args):
    m = manifest_lesen()
    dateien = [] if args.nur_manifest else [
        (f"mitori-{b['id']}", b["version"], v["datei"], GEHEIM / "aus" / b["id"] / str(b["version"]) / v["datei"])
        for b in m["bundles"] for v in b["videos"]]
    if args.probe:
        for paket, version, name, pfad in dateien:
            groesse = f"{pfad.stat().st_size / (1 << 20):.0f} MiB" if pfad.exists() else "FEHLT"
            print(f"{BASIS}/{paket}/{version}/{name}  {groesse}")
        print(f"{BASIS}/{'/'.join(MANIFEST_PAKET[:2])}/{MANIFEST_PAKET[2]}")
        return
    if not args.verband_stimmt_zu:
        sys.exit("bundle: hochladen nur mit --verband-stimmt-zu (die Zustimmung des Verbands liegt vor)")
    # Alles vor dem ersten Request: was hier scheitert, hat den Rechner nicht verlassen.
    for b in m["bundles"]:
        if ist_testbau(b):
            sys.exit(f"bundle: {b['id']} ist ein Testbau (unbeschnittene Originale), nichts wird hochgeladen")
    for _, _, _, pfad in dateien:
        if pfad.exists():
            verschluesselt_pruefen(pfad)
    if not args.nur_manifest:
        if not m["bundles"]:
            sys.exit(f"bundle: keine Bundles in {GEHEIM}, nichts wird hochgeladen")
        if not shutil.which("ffprobe"):
            sys.exit("bundle: ohne ffprobe keine Prüfung der Videos, nichts wird hochgeladen")
        fehler = [f for b in m["bundles"] for f in verifiziert(b["id"])]
        if fehler:
            sys.exit("bundle: " + "; ".join(fehler) + "; nichts wird hochgeladen")
    token = (GEHEIM / "gitea-token").read_text().strip()
    for paket, version, name, pfad in dateien:
        with open(pfad, "rb") as f:
            hochladen(paket, version, name, f, token, pfad.stat().st_size)
    hochladen(*MANIFEST_PAKET, json.dumps(m, ensure_ascii=False, indent=1).encode(), token)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="befehl", required=True)
    b = sub.add_parser("build")
    b.add_argument("bundle")
    b.add_argument("--videos", default=str(WURZEL.parent / "Mitori Videos"))
    b.add_argument("--version", type=int)
    b.add_argument("--hinweis", help="was die neue Version bringt (Update-Hinweis in der App)")
    b.add_argument("--ohne-kodieren", action="store_true", help="Originale verschlüsseln (Test)")
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
    a.add_argument("--videos", default=str(WURZEL.parent / "Mitori Videos"))
    a.add_argument("--hinweis")
    a.add_argument("--ohne-kodieren", action="store_true")
    r = sub.add_parser("verifizieren")
    r.add_argument("bundle", nargs="?")
    sub.add_parser("stand")
    args = p.parse_args()
    {"build": befehl_build, "codes": befehl_codes, "sperren": befehl_sperren, "pruefen": befehl_pruefen,
     "hochladen": befehl_hochladen, "alle": befehl_alle, "verifizieren": befehl_verifizieren,
     "stand": befehl_stand}[args.befehl](args)


if __name__ == "__main__":
    main()
