#!/usr/bin/env python3
"""Prüft die Programmdaten in daten/ und erzeugt daraus Heft- und App-Daten.

Aufruf aus dem Projektordner:  python3 tools/daten.py [--ausgabe build/daten]

Eingabe (daten/):
  aikido.yaml, daitoryu.yaml   Prüfungsprogramme (Aufbau im Kopf von aikido.yaml)
  shinki-toho.yaml             Grade, Kamae, Suburi, Ô-dachi-Formen
  shinki-toho-kommentare.yaml  Kommentare von shinkiryu.de (erzeugt von tools/kommentare.py)
  lexikon.yaml                 Aiki-Budo-Lexikon Japanisch–Deutsch (erzeugt von tools/lexikon.py)
  ../pakete/*.yaml             Lernpakete (pakete/README.md), nur geprüft (tools/paket.py), nicht in der Ausgabe
  videos.yaml                  Videostelle je Technik (erzeugt von tools/kapitel.py, von Hand geprüft)
  begriffe.yaml                Kanji (Aikido, Shinki Toho), gesichert
  daitoryu-begriffe.yaml       Kanji-Bausteine Daitoryu, ungeprüft
  englisch-*.yaml              Englisch zu jedem deutschen Text, nur für die App (Abschnitt „Englisch“ unten)
  ../KORREKTUREN.md            offene Fragen; jede Frage-ID der Daten muss dort stehen

Ausgabe (build/daten/):
  <disziplin>.lua              für das Heft (mitori-heft, heft/lua/mitori-heft.lua), Kanji schon eingesetzt
  stand.lua                    der Datenstand aus STAND, für den Titel des Hefts
  mitori-daten.json            für die App: der Datenstand (stand), jede Technik einzeln mit fester ID, Videostellen,
                               je Video Datei (relativ zum Videoordner) und Beschnitt; das Glossar
                               (Lexikon und Begriffe ohne Lexikon-Eintrag, alphabetisch)
  fehlende-kanji.txt           Namen, zu denen es kein Kanji gibt

Bricht mit Exit-Code 1 ab, wenn die Daten Fehler haben (unbekannter Grad, unbekannte
Frage-ID, unbekannter Schlüssel, Text ohne Englisch).
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import NamedTuple

import yaml

WURZEL = Path(__file__).resolve().parent.parent
DATEN = WURZEL / "daten"
FORMAT = 1  # Version des App-Formats; erhöhen, wenn sich mitori-daten.json inkompatibel ändert
STAND = WURZEL / "STAND"  # Datenstand, den App und Heft anzeigen; das Tag dazu heißt v<Stand>

fehler: list[str] = []
fehlend: set[str] = set()
texte: list["Text"] = []  # jeder Text mit Ort und Englisch, für tools/uebersetzung.py


def melde(text):
    fehler.append(text)


# --- Namen und Kanji ---------------------------------------------------------

def schluessel(name):
    """klein, ohne Längenzeichen (ô → o)"""
    zerlegt = unicodedata.normalize("NFD", name)
    return "".join(z for z in zerlegt if unicodedata.category(z) != "Mn").lower()


def flach(name):
    """Aikido-Glossar: zusätzlich ohne Bindestriche und Leerzeichen"""
    return re.sub(r"[- ]", "", schluessel(name))


def kennung(text):
    """ID-Teil: klein, ASCII, Bindestriche"""
    return re.sub(r"[^a-z0-9]+", "-", schluessel(text).replace("'", "")).strip("-")


class Glossar:
    def __init__(self, datei, bausteine):
        roh = yaml.safe_load((DATEN / datei).read_text(encoding="utf-8"))
        self.bausteine = bausteine
        self.tabelle = {(schluessel(k) if bausteine else flach(k)): v for k, v in roh.items()}

    def _zusammensetzen(self, name):
        ganz = self.tabelle.get(schluessel(name))
        if ganz:
            return ganz
        teile = schluessel(name).split("-")
        erg, i = [], 0
        while i < len(teile):
            for j in range(len(teile), i, -1):
                k = "-".join(teile[i:j])
                if k in self.tabelle:
                    erg.append(self.tabelle[k])
                    i = j
                    break
            else:
                return None
        return "".join(erg)

    def kanji(self, art, name, leise=False):
        if not name:
            return None
        k = self._zusammensetzen(name) if self.bausteine else self.tabelle.get(flach(name))
        if k is None and not leise:
            fehlend.add(f"{art}: {name}")
        return k


def eintrag(text):
    """'Technik (Zusatz) [Frage Frage]' zerlegen"""
    fragen = []
    m = re.search(r"\s*\[(.*?)\]", text)
    if m:
        fragen = m.group(1).split()
        text = text[: m.start()] + text[m.end():]
    m = re.match(r"^(.*?)\s+\((.*)\)$", text)
    name, zusatz = (m.group(1), m.group(2)) if m else (text, None)
    return {"name": name.strip(), "zusatz": zusatz, "fragen": fragen}


# --- Korrekturliste ----------------------------------------------------------

def korrekturen(datei=WURZEL / "KORREKTUREN.md"):
    """Status je Frage-ID. Die Spalte heißt in jeder Tabelle „Status“; danach dürfen weitere
    folgen (z. B. „Entscheidung vom Owner“)."""
    ids = {}
    spalte = None
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        zellen = [z.strip() for z in zeile.strip().strip("|").split("|")]

        # Kopfzeile einer Tabelle: dort steht, die wievielte Spalte der Status ist.
        if zellen and zellen[0] == "ID":
            spalte = zellen.index("Status") if "Status" in zellen else None
            continue

        if spalte is None or not re.fullmatch(r"[ADS]-[A-Z0-9-]+", zellen[0]) or len(zellen) <= spalte:
            continue
        ids[zellen[0]] = zellen[spalte]
    return ids


def pruefe_fragen(fragen, wo, ids):
    for f in fragen:
        if f not in ids:
            melde(f"{wo}: Frage {f} fehlt in KORREKTUREN.md")
        elif ids[f] != "klären":
            melde(f"{wo}: Frage {f} hat Status „{ids[f]}“; Marke aus den Daten nehmen oder Status ändern")


# --- Prüfungsprogramme (Aikido, Daitoryu) -----------------------------------

ANGRIFF_FELDER = {"angriff", "zusatz", "frage"}
GRUPPEN_FELDER = {"titel", "begriff", "ohne_angriff", "text", "frage", "angriffe", "fuss"}


def programm(art, ids, gloss):
    d = yaml.safe_load((DATEN / f"{art}.yaml").read_text(encoding="utf-8"))
    alle_grade = {g["id"] for g in d["grade"]}
    vorschlag = gloss.bausteine

    def jp_begriff(b):
        if not b:
            return None
        liste = [b] if isinstance(b, str) else b
        return "　".join(gloss.kanji(art, x) or "" for x in liste)

    heft = {k: d[k] for k in ("kurz", "titel", "untertitel", "jp", "stand", "vorbemerkung") if k in d}
    heft.update(vorschlag=vorschlag, grade=d["grade"], teile=[])
    app_gruppen, app_techniken = [], []

    for teil in d["teile"]:
        for gid in teil["grade"]:
            if gid not in alle_grade:
                melde(f"{art}, {teil['titel']}: unbekannter Grad {gid}")
        h_teil = {"titel": teil["titel"], "grade": teil["grade"], "gruppen": []}
        heft["teile"].append(h_teil)
        for gr in teil["gruppen"]:
            wo_g = f"{art}, {teil['titel']}, {gr['titel']}"
            for k in gr:
                if k not in GRUPPEN_FELDER:
                    melde(f"{wo_g}: unbekanntes Feld {k}")
            pruefe_fragen([gr["frage"]] if gr.get("frage") else [], wo_g, ids)
            ohne = bool(gr.get("ohne_angriff"))
            text = bool(gr.get("text"))
            g_id = f"{art}/{kennung(teil['titel'])}/{kennung(gr['titel'])}"
            h_gr = {"titel": gr["titel"], "jp": jp_begriff(gr.get("begriff")), "frage": gr.get("frage"),
                    "ohne_angriff": ohne, "text": text, "fuss": gr.get("fuss"), "angriffe": []}
            h_teil["gruppen"].append(h_gr)
            app_gruppen.append({"id": g_id, "teil": teil["titel"], "titel": gr["titel"], "jp": h_gr["jp"],
                                "art": "text" if text else ("ohne_angriff" if ohne else "angriffe")})
            for a in gr["angriffe"]:
                wo = f"{wo_g}, {a.get('angriff') or '–'}"
                for k in a:
                    if k not in ANGRIFF_FELDER and k not in teil["grade"]:
                        melde(f"{wo}: unbekanntes Feld oder Grad {k}")
                pruefe_fragen([a["frage"]] if a.get("frage") else [], wo, ids)
                name, zusatz = a.get("angriff"), a.get("zusatz")
                k1 = None if (ohne or text) else gloss.kanji(art, name)
                k2 = gloss.kanji(art, zusatz, leise=True) if (k1 and zusatz) else None
                a_jp = (k1 + "・" + k2) if (k1 and k2) else k1
                h_a = {"angriff": name, "zusatz": zusatz, "jp": a_jp, "frage": a.get("frage"), "techniken": {}}
                h_gr["angriffe"].append(h_a)
                a_id = kennung(" ".join(x for x in (name, zusatz) if x)) or "ohne"
                for gid in teil["grade"]:
                    liste = []
                    for nr, roh in enumerate(a.get(gid) or [], 1):
                        e = eintrag(roh)
                        pruefe_fragen(e["fragen"], f"{wo}, {gid}, {e['name']}", ids)
                        e["jp"] = None if text else gloss.kanji(art, e["name"])
                        liste.append(e)
                        app_techniken.append({
                            "id": f"{g_id}/{a_id}/{gid}/{kennung(e['name'])}-{nr}",
                            "gruppe": g_id, "grad": gid,
                            "angriff": None if ohne or text else {"name": name, "zusatz": zusatz, "jp": a_jp},
                            "name": e["name"], "zusatz": e["zusatz"], "jp": e["jp"],
                            "fragen": e["fragen"] + ([a["frage"]] if a.get("frage") else []),
                        })
                    if liste:
                        h_a["techniken"][gid] = liste
    app = {"id": art, "titel": d["titel"], "kurzname": d["kurzname"], "untertitel": d.get("untertitel"), "jp": d.get("jp"),
           "stand": d.get("stand"), "kanji_vorschlag": vorschlag, "grade": grade_app(art, d["grade"]),
           "teile": [{"titel": t["titel"], "grade": t["grade"]} for t in d["teile"]],
           "gruppen": app_gruppen, "techniken": app_techniken}
    return heft, app


# --- Wartezeiten ---------------------------------------------------------------

ABSTAND = re.compile(r"(\d+) Jahre?( nach Trainingsbeginn)?")


def grade_app(art, grade):
    """Grade für die App: `abstand` ("2 Jahre", "2 Jahre nach Trainingsbeginn") auch als
    `wartezeit` {jahre, nach: "grad" | "beginn"}; `pruefbar` false für Grade ohne Prüfung (Hôshu).
    Jeder prüfbare Grad außer dem ersten braucht einen Abstand."""
    ergebnis = []
    for i, g in enumerate(grade):
        g = dict(g, pruefbar=g.get("pruefbar", True), wartezeit=None)
        abstand = g.get("abstand")
        if abstand:
            m = ABSTAND.fullmatch(abstand)
            if not m:
                melde(f"{art}, Grad {g['name']}: Abstand „{abstand}“ nicht lesbar (\"N Jahr(e) [nach Trainingsbeginn]\")")
            elif m.group(2) and i > 0:
                melde(f"{art}, Grad {g['name']}: „nach Trainingsbeginn“ nur beim ersten Grad")
            else:
                g["wartezeit"] = {"jahre": int(m.group(1)), "nach": "beginn" if m.group(2) else "grad"}
        elif g["pruefbar"] and i > 0:
            melde(f"{art}, Grad {g['name']}: Abstand fehlt (oder pruefbar: false)")
        ergebnis.append(g)
    return ergebnis


# --- Shinki Toho -------------------------------------------------------------

def positionen(indizes):
    """Nummern der Kamae-Positionen (wie im Blatt und im Heft, ab 1) eines Kommentars: [1, 2] → "2–3"."""
    erste, letzte = indizes[0] + 1, indizes[-1] + 1
    return str(erste) if erste == letzte else f"{erste}–{letzte}"


def shinki_toho(ids):
    d = yaml.safe_load((DATEN / "shinki-toho.yaml").read_text(encoding="utf-8"))
    for g in d["grade"]:
        pruefe_fragen([g["frage"]] if g.get("frage") else [], f"shinki-toho, Grad {g['name']}", ids)
    nummern = [f["nr"] for f in d["odachi"]]
    if nummern != list(range(1, len(nummern) + 1)):
        melde("shinki-toho: Ô-dachi-Nummern nicht fortlaufend")
    for f in d["odachi"]:
        pruefe_fragen((f.get("frage") or "").split(), f"shinki-toho, Ô-dachi {f['nr']}", ids)
        for k in ("name", "uchidachi", "shidachi", "treffer", "zanshin"):
            if not f.get(k):
                melde(f"shinki-toho, Ô-dachi {f['nr']}: {k} fehlt")
    app = dict(d, id="shinkitoho")
    app["grade"] = grade_app("shinki-toho", d["grade"])
    app["odachi"] = [dict(f, id=f"shinkitoho/odachi/{f['nr']}", fragen=(f.get("frage") or "").split())
                     for f in d["odachi"]]
    for f in app["odachi"]:
        f.pop("frage", None)
    # Die Kamae-Übung ist ein Ablauf: ein Eintrag, die Positionen sind seine Beschreibung.
    kamae = d["abschnitte"]["kamae"]
    app["kamae"] = {"id": "shinkitoho/kamae", "name": kamae["name"], "kanji": kamae["kanji"], "positionen": d["kamae"]}
    app["suburi"] = [dict(s, id=f"shinkitoho/suburi/{i}") for i, s in enumerate(d["suburi"], 1)]
    app["kiriotoshi"] = dict(d["kiriotoshi"], id="shinkitoho/kiriotoshi")

    # Kommentare von shinkiryu.de (tools/kommentare.py), nur für die App
    k = yaml.safe_load((DATEN / "shinki-toho-kommentare.yaml").read_text(encoding="utf-8"))
    app["kommentare_quelle"] = k["quelle"]
    app["kiriotoshi"]["kommentar"] = {"titel": f"Grundübung: {app['kiriotoshi']['name']}", "text": k["kiriotoshi"]}
    kumi = d["abschnitte"]["kumidachi"]
    app["kumidachi"] = dict(kumi, id="shinkitoho/kumidachi",
                            kommentar={"titel": f"{kumi['name']} · {kumi['text'].split(':')[0]}", "text": k["kumidachi"]})
    for s, ks in zip(app["suburi"], k["suburi"], strict=True):
        s["kommentar"] = {"titel": ks["titel"], "text": ks["text"]}
    app["kamae"]["kommentar"] = {"titel": kamae["name"],
                                 "text": "\n\n".join(f"{positionen(kk['kamae'])}. {kk['titel']}\n{kk['text']}" for kk in k["kamae"])}
    for f, kf in zip(app["odachi"], k["odachi"], strict=True):
        f["kommentar"] = {"titel": f"{kf['nr']}. {kf['titel']}", "text": kf["text"]}
    return d, app


# --- Glossar -----------------------------------------------------------------

# Schlüssel in begriffe.yaml, die deutsche Wörter sind, keine japanischen Begriffe.
NICHT_JAPANISCH = {"diagonal", "gerade", "Sonstige Techniken"}


def stichwort(wort):
    """Lexikon-Wort ohne Zusatz in Klammern: kime (-gime) → kime"""
    return re.sub(r"\s*\(.*$", "", wort).strip()


def zweitform(wort):
    """Die Schreibweise in Klammern, falls es eine ist: Kubi-shime (-jime) → Kubi-jime,
    Mune-tori (Muna-dori) → Muna-dori; Erklärungen (Verb: fuseru) → None."""
    m = re.search(r"\((?:bzw\.\s*)?(-?[A-Za-z][a-z-]*|-[a-z-]+)\)", wort)
    if not m:
        return None
    zweit, grund = m.group(1).lower(), stichwort(wort)
    if not zweit.startswith("-"):
        return zweit
    return grund.rsplit("-", 1)[0] + zweit if "-" in grund else zweit[1:]


def glossar_schluessel(name):
    """Vergleich im Glossar: wie flach, dazu oo wie o (Oo-guruma = O-guruma)"""
    return flach(name).replace("oo", "o")


def offene_begriffe(ids):
    """Begriffe in begriffe.yaml, deren Kanji eine offene Frage hat (Kommentar mit ID, Status klären)."""
    offen = set()
    for zeile in (DATEN / "begriffe.yaml").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([^#:][^:]*):.*#.*?\b([ADS]-[A-Z0-9]+(?:-[A-Z0-9]+)*)", zeile)
        if m and ids.get(m.group(2)) == "klären":
            offen.add(m.group(1).strip())
    return offen


# Hepburn-Silben als Hiragana, längste zuerst gesucht (Aussprache per Sprachsynthese).
KANA = dict(zip(
    "a i u e o ka ki ku ke ko sa shi su se so ta chi tsu te to na ni nu ne no ha hi fu he ho "
    "ma mi mu me mo ya yu yo ra ri ru re ro wa wo ga gi gu ge go za ji zu ze zo da di du de do "
    "ba bi bu be bo pa pi pu pe po si ti tu hu zi "
    "kya kyu kyo sha shu sho cha chu cho nya nyu nyo hya hyu hyo mya myu myo rya ryu ryo "
    "gya gyu gyo ja ju jo bya byu byo pya pyu pyo".split(),
    "あ い う え お か き く け こ さ し す せ そ た ち つ て と な に ぬ ね の は ひ ふ へ ほ "
    "ま み む め も や ゆ よ ら り る れ ろ わ を が ぎ ぐ げ ご ざ じ ず ぜ ぞ だ ぢ づ で ど "
    "ば び ぶ べ ぼ ぱ ぴ ぷ ぺ ぽ し ち つ ふ じ "
    "きゃ きゅ きょ しゃ しゅ しょ ちゃ ちゅ ちょ にゃ にゅ にょ ひゃ ひゅ ひょ みゃ みゅ みょ りゃ りゅ りょ "
    "ぎゃ ぎゅ ぎょ じゃ じゅ じょ びゃ びゅ びょ ぴゃ ぴゅ ぴょ".split(), strict=True))
ZAHLEN = dict(zip("123456789", "いち に さん よん ご ろく なな はち きゅう".split(), strict=True))
LANG = {"â": "aa", "î": "ii", "û": "uu", "ê": "ee", "ô": "ou", "ā": "aa", "ī": "ii", "ū": "uu", "ē": "ee", "ō": "ou"}


def kana(wort):
    """Lesung in Hiragana aus der Umschrift: "Kiri-otoshi" → きりおとし, "Ikkajô" → いっかじょう,
    "San'nin" → さんにん; None, wenn ein Teil keine Silbe ist."""
    text = "".join(LANG.get(z, z) for z in stichwort(wort).lower())
    text = re.sub(r"oh(?![aiueoy])", "ou", text)        # Shikkoh: langes o
    text = text.replace("!", "")
    aus, i = [], 0
    while i < len(text):
        z = text[i]
        if z == " ":
            aus.append("　")
        elif z in ZAHLEN:
            aus.append(ZAHLEN[z])
        elif z in "'-":                                  # Silbengrenze: Shomen-uchi, San'nin
            pass
        elif z == "n" and (i + 1 == len(text) or text[i + 1] not in "aiueoy"):
            aus.append("ん")
        elif z == "m" and text[i + 1:i + 2] in ("b", "p", "m"):    # Sempai
            aus.append("ん")
        elif z in "kstpgcbdfhjmrz" and text[i + 1:i + 2] == z or text[i:i + 3] == "tch":
            aus.append("っ")
        else:
            silbe = next((text[i:j] for j in (i + 3, i + 2, i + 1) if text[i:j] in KANA), None)
            if silbe is None:
                return None
            aus.append(KANA[silbe])
            i += len(silbe)
            continue
        i += 1
    return "".join(aus)


def wortgrenzen(wort, bekannt):
    """Setzt Bindestriche, wo ein zusammengeschriebenes Wort aus bekannten Wörtern besteht und nach
    einem n ein Vokal folgt: Yokomenuchi → yokomen-uchi (よこめんうち, nicht よこめぬち)."""
    text = stichwort(wort).lower()
    if not re.search(r"n[aiueoy]", text) or re.search(r"[- ]", text):
        return wort

    def teile(rest):
        if rest in bekannt:
            return [rest]
        for j in range(len(rest) - 1, 1, -1):
            if rest[:j] in bekannt and (weiter := teile(rest[j:])):
                return [rest[:j]] + weiter
        return None

    bekannt = bekannt - {text}                          # aus anderen Wörtern, nicht aus sich selbst
    stuecke = teile(text)
    if not stuecke:
        return wort
    aus = stuecke[0]
    for t in stuecke[1:]:
        aus += ("-" if aus.endswith("n") and t[0] in "aiueoy" else "") + t
    return aus


def glossar(ids):
    """Das Glossar der App: das Aiki-Budo-Lexikon, ergänzt um die Begriffe aus begriffe.yaml, die
    es nicht kennt (ohne Übersetzung). Hat ein Lexikon-Wort kein Kanji, kommt es aus begriffe.yaml.
    Ein Begriff gilt als bekannt, wenn er dem Stichwort oder der Schreibweise in Klammern gleicht
    (Kubi-jime = Kubi-shime (-jime)); Begriffe mit offener Kanji-Frage bleiben draußen.
    Je Wort: wort (wie im Lexikon, erster Buchstabe groß), jp (oder None), de (oder ""), kana (die
    Lesung für die Sprachsynthese, oder None)."""
    lexikon = yaml.safe_load((DATEN / "lexikon.yaml").read_text(encoding="utf-8"))
    begriffe = yaml.safe_load((DATEN / "begriffe.yaml").read_text(encoding="utf-8"))
    for k in NICHT_JAPANISCH - begriffe.keys():
        melde(f"daten.py NICHT_JAPANISCH: {k} fehlt in begriffe.yaml")
    offen = offene_begriffe(ids)

    woerter = [{"wort": w["wort"][:1].upper() + w["wort"][1:], "jp": w["jp"], "de": w["de"]}
               for w in lexikon["woerter"]]
    nach_schluessel = {}
    for w in woerter:
        for form in {stichwort(w["wort"]), zweitform(w["wort"])} - {None}:
            nach_schluessel.setdefault(glossar_schluessel(form), []).append(w)

    for name, jp in begriffe.items():
        if name in NICHT_JAPANISCH or name in offen:
            continue
        gleiche = nach_schluessel.get(glossar_schluessel(name))
        if not gleiche:
            woerter.append({"wort": name, "jp": jp, "de": ""})
            continue
        if len(gleiche) == 1 and not gleiche[0]["jp"]:     # bei zwei Wörtern (kata: 型, 肩) unklar, welches
            gleiche[0]["jp"] = jp

    bekannt = {stichwort(w["wort"]).lower() for w in woerter}
    for w in woerter:
        w["kana"] = kana(wortgrenzen(w["wort"], bekannt))
    woerter.sort(key=lambda w: (schluessel(w["wort"]), w["jp"] or ""))
    return {"quelle": lexikon["quelle"], "woerter": woerter}


# --- Englisch ----------------------------------------------------------------

# Paare {de, en} und die Liste der Texte, die englisch gleich bleiben (japanische Namen).
# Der Schlüssel ist der deutsche Text selbst: Ändert er sich (auch in den erzeugten Dateien, die man
# nicht von Hand bearbeitet), fehlt das Englisch und der Lauf bricht ab, statt Veraltetes auszuliefern.
#
#   daten/aikido.yaml                    → "2 Arten"
#   daten/englisch-programm.yaml         → {de: "2 Arten", en: "2 variants"}
#   mitori-daten.json                    → "zusatz": "2 Arten", "zusatz_en": "2 variants"
#
# In der JSON steht neben einem Feld x das Feld x_en, nur wenn es sich unterscheidet; sonst gilt x.
# Das Glossar nennt die Übersetzung von `de` schlicht `en`. Das Heft bekommt kein Englisch.
ENGLISCH_PAARE = ("englisch-programm.yaml", "englisch-kommentare.yaml", "englisch-lexikon.yaml")
ENGLISCH_GLEICH = "englisch-gleich.yaml"
ABSATZ = "\n\n"
UEBERSCHRIFT = "## "
ANGEHAENGT = "_en"


class Text(NamedTuple):
    bereich: str    # Gruppe auf der Prüfseite, Ebenen mit " › " getrennt
    ort: str        # ID oder Pfad in den Daten
    feld: str
    de: str
    en: str | None  # None: fehlt


def absatzform(text):
    """Absätze und Überschriften eines Textes; Deutsch und Englisch müssen gleich gebaut sein."""
    teile = text.split(ABSATZ)
    return len(teile), [i for i, t in enumerate(teile) if t.startswith(UEBERSCHRIFT)]


class Englisch:
    def __init__(self, paare, gleich):
        self.paare = paare
        self.gleich = gleich
        self.benutzt = set()

    @classmethod
    def laden(cls):
        """Liest daten/englisch-*.yaml; ein Text mit zwei Übersetzungen ist ein Fehler."""
        paare = {}
        for datei in ENGLISCH_PAARE:
            for p in yaml.safe_load((DATEN / datei).read_text(encoding="utf-8")):
                if paare.setdefault(p["de"], p["en"]) != p["en"]:
                    melde(f"{datei}: zwei Übersetzungen für „{p['de'][:60]}“")
                if p["de"] == p["en"]:
                    melde(f"{datei}: „{p['de'][:60]}“ ist gleich, gehört nach {ENGLISCH_GLEICH}")
        gleich = set(yaml.safe_load((DATEN / ENGLISCH_GLEICH).read_text(encoding="utf-8")))
        for de in gleich & paare.keys():
            melde(f"{ENGLISCH_GLEICH}: „{de[:60]}“ hat auch eine Übersetzung")
        return cls(paare, gleich)

    def text(self, bereich, ort, feld, de):
        """Das Englisch zu einem Text (None, wenn es fehlt); merkt den Text für die Prüfseite."""
        en = de if de in self.gleich else self.paare.get(de)
        self.benutzt.add(de)
        texte.append(Text(bereich, ort, feld, de, en))
        if en is None:
            melde(f"{ort}, {feld}: Englisch fehlt für „{de[:60]}“")
        elif absatzform(en) != absatzform(de):
            melde(f"{ort}, {feld}: Absätze oder Überschriften anders als im Deutschen: „{de[:60]}“")
        return en

    def feld(self, bereich, ort, ziel, feld, neu=None):
        """Setzt neben ziel[feld] das Englisch, falls es sich unterscheidet: name → name_en."""
        de = ziel.get(feld)
        if not de:
            return
        en = self.text(bereich, ort, feld, de)
        if en and en != de:
            ziel[neu or feld + ANGEHAENGT] = en

    def felder(self, bereich, ort, ziel, felder):
        for f in felder:
            self.feld(bereich, ort, ziel, f)

    def rest(self):
        """Einträge, zu denen es keinen Text mehr gibt: die Übersetzung ist veraltet."""
        return sorted((self.paare.keys() | self.gleich) - self.benutzt)


def englisch_disziplin(en, d):
    """Grade und Überschriften, die jede Disziplin hat."""
    name = d["kurzname"]
    en.felder(f"{name} › Allgemein", d["id"], d, ("titel", "kurzname", "untertitel", "stand"))
    for g in d["grade"]:
        en.felder(f"{name} › Grade", f"{d['id']}/{g['id']}", g, ("name", "kurzname", "bedeutung", "inhalt", "abstand"))


def englisch_programm(en, d):
    """Aikido, Daitoryu: Gruppen und Techniken. `fuss` steht nur im Heft, daher kein Feld in der JSON."""
    name = d["kurzname"]
    for t in d["teile"]:
        en.feld(f"{name} › Teile und Gruppen", f"{d['id']}/{kennung(t['titel'])}", t, "titel")
    titel = {}
    for g in d["gruppen"]:
        en.felder(f"{name} › Teile und Gruppen", g["id"], g, ("titel", "teil"))
        titel[g["id"]] = f"{name} › {g['teil']} › {g['titel']}"
    for t in d["techniken"]:
        bereich = titel[t["gruppe"]]
        en.felder(bereich, t["id"], t, ("name", "zusatz"))
        if t["angriff"]:
            en.felder(bereich, f"{t['id']} (Angriff)", t["angriff"], ("name", "zusatz"))
    quelle = yaml.safe_load((DATEN / f"{d['id']}.yaml").read_text(encoding="utf-8"))
    for teil in quelle["teile"]:
        for g in teil["gruppen"]:
            if g.get("fuss"):
                en.text(f"{name} › Nur im Heft", f"{d['id']}/{kennung(teil['titel'])}/{kennung(g['titel'])}", "fuss", g["fuss"])


def englisch_vorbemerkung(en, datei, bereich):
    """Vorbemerkung des Hefts, je Absatz ein Text. Die App zeigt sie nicht, daher kein Feld in der JSON."""
    zeilen = (DATEN / datei).read_text(encoding="utf-8").splitlines()
    absaetze = "\n".join(z for z in zeilen if not z.startswith("%")).strip().split(ABSATZ)
    for i, absatz in enumerate(absaetze, 1):
        en.text(bereich, datei, f"Absatz {i}", absatz)


def englisch_kommentar(en, bereich, e):
    en.felder(bereich, e["id"], e["kommentar"], ("titel", "text"))


def englisch_kamae(en, kamae):
    """Der Kommentar der Kamae-Übung ist aus 24 Stücken gebaut (shinki_toho): englisch genauso."""
    bereich = "Shinki Toho › Kommentare › Kamae"
    teile = []
    for kk in yaml.safe_load((DATEN / "shinki-toho-kommentare.yaml").read_text(encoding="utf-8"))["kamae"]:
        ort = f"shinkitoho/kamae/{kk['nr']}"
        teile.append((positionen(kk["kamae"]), en.text(bereich, ort, "titel", kk["titel"]),
                      en.text(bereich, ort, "text", kk["text"])))
    en.feld(bereich, kamae["id"], kamae["kommentar"], "titel")
    if all(titel and text for _, titel, text in teile):
        kamae["kommentar"]["text_en"] = ABSATZ.join(f"{nr}. {titel}\n{text}" for nr, titel, text in teile)


def englisch_shinki_toho(en, d):
    name = d["kurzname"]
    zulassung = [en.text(f"{name} › Zulassung", f"{d['id']}/zulassung/{i}", "text", t)
                 for i, t in enumerate(d["zulassung"], 1)]
    if all(zulassung):
        d["zulassung_en"] = zulassung
    for art, a in d["abschnitte"].items():
        en.felder(f"{name} › Abschnitte", f"{d['id']}/abschnitte/{art}", a, ("name", "text"))

    en.feld(f"{name} › Kamae", d["kamae"]["id"], d["kamae"], "name")
    for i, p in enumerate(d["kamae"]["positionen"], 1):
        en.feld(f"{name} › Kamae", f"{d['kamae']['id']}/{i}", p, "name")
    for s in d["suburi"]:
        en.felder(f"{name} › Suburi", s["id"], s, ("name", "text"))
        englisch_kommentar(en, f"{name} › Kommentare › Suburi", s)
    for art in ("kiriotoshi", "kumidachi"):
        en.felder(f"{name} › {d[art]['name']}", d[art]["id"], d[art], ("name", "text"))
        englisch_kommentar(en, f"{name} › Kommentare › {d[art]['name']}", d[art])
    for f in d["odachi"]:
        en.felder(f"{name} › Ô-dachi", f["id"], f, ("name", "uchidachi", "shidachi", "treffer", "zanshin"))
        englisch_kommentar(en, f"{name} › Kommentare › Ô-dachi", f)
    englisch_kamae(en, d["kamae"])
    en.feld(f"{name} › Allgemein", d["id"], d["kommentare_quelle"], "titel")


def englisch_glossar(en, glossar_app):
    en.feld("Glossar › Quelle", "glossar", glossar_app, "quelle")
    for w in glossar_app["woerter"]:
        en.feld("Glossar › Wörter", w["wort"], w, "wort")
        en.feld("Glossar › Wörter", w["wort"], w, "de", "en")


def englisch(disziplinen, glossar_app):
    """Hängt das Englisch an die App-Daten. Erst aufrufen, wenn die *.lua geschrieben sind: Die App-Daten
    teilen sich Objekte mit dem Heft (Kamae-Positionen), und das Heft bekommt kein Englisch."""
    en = Englisch.laden()
    for d in disziplinen:
        englisch_disziplin(en, d)
        if "techniken" in d:
            englisch_programm(en, d)
        else:
            englisch_shinki_toho(en, d)
    englisch_vorbemerkung(en, "aikido-vorbemerkung.tex", "Aikido › Nur im Heft")
    englisch_glossar(en, glossar_app)
    for de in en.rest():
        melde(f"daten/englisch-*.yaml: zu „{de[:60]}“ gibt es keinen Text mehr")


# --- Ausgabe -----------------------------------------------------------------

def lua(wert, tiefe=0):
    """Python-Wert als Lua-Ausdruck"""
    if wert is None:
        return "nil"
    if isinstance(wert, bool):
        return "true" if wert else "false"
    if isinstance(wert, (int, float)):
        return repr(wert)
    if isinstance(wert, str):
        return json.dumps(wert, ensure_ascii=False)  # JSON-Strings sind gültige Lua-Strings
    ein = "  " * (tiefe + 1)
    if isinstance(wert, list):
        return "{\n" + "".join(f"{ein}{lua(v, tiefe + 1)},\n" for v in wert) + "  " * tiefe + "}"
    teile = [f"{ein}[{json.dumps(k, ensure_ascii=False)}] = {lua(v, tiefe + 1)},\n"
             for k, v in wert.items() if v is not None]
    return "{\n" + "".join(teile) + "  " * tiefe + "}"


def videostellen(disziplinen):
    """Hängt an jeden Eintrag mit Kapitel in daten/videos.yaml seine Videostelle (video, von, bis)."""
    datei = DATEN / "videos.yaml"
    if not datei.exists():
        return 0, {}
    eintraege = {}
    for d in disziplinen:
        for e in d.get("techniken", []):
            eintraege[e["id"]] = e
        for art in ("suburi", "odachi"):
            for e in d.get(art, []):
                eintraege[e["id"]] = e
        for art in ("kamae", "kiriotoshi"):
            if art in d:
                eintraege[d[art]["id"]] = d[art]
    gesetzt = 0
    alle = yaml.safe_load(datei.read_text(encoding="utf-8")) or {}
    for video, inhalt in alle.items():
        for k in inhalt["kapitel"]:
            ziel = eintraege.get(k["id"])
            if ziel is None:
                melde(f"videos.yaml {video}: unbekannte ID {k['id']}")
            elif not k.get("fehlt"):
                ziel["video"] = {"video": video, "von": k["von"], "bis": k["bis"]}
                gesetzt += 1
    return gesetzt, {v: {"datei": i["datei"], "beschnitt": i["beschnitt"]} for v, i in alle.items()}


def datenstand():
    stand = STAND.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d{4}\.\d{1,2}\.\d+", stand):
        fehler.append(f"STAND: {stand!r} ist nicht JJJJ.M.N")
    return stand


def erzeuge(ausgabe):
    """Schreibt alle Ausgaben nach `ausgabe`; Fehler sammelt `fehler`, Texte sammelt `texte`."""
    ausgabe.mkdir(parents=True, exist_ok=True)

    ids = korrekturen()
    aikido_gloss = Glossar("begriffe.yaml", bausteine=False)
    disziplinen = []
    for art, gloss in (("aikido", aikido_gloss), ("daitoryu", Glossar("daitoryu-begriffe.yaml", bausteine=True))):
        heft, app = programm(art, ids, gloss)
        disziplinen.append(app)
        (ausgabe / f"{art}.lua").write_text(
            "-- erzeugt von tools/daten.py aus daten/" + art + ".yaml, nicht von Hand bearbeiten\nreturn "
            + lua(heft) + "\n", encoding="utf-8")
    st_heft, st_app = shinki_toho(ids)
    disziplinen.append(st_app)
    (ausgabe / "shinki-toho.lua").write_text(
        "-- erzeugt von tools/daten.py aus daten/shinki-toho.yaml, nicht von Hand bearbeiten\nreturn "
        + lua(st_heft) + "\n", encoding="utf-8")

    mit_video, videos = videostellen(disziplinen)
    import paket    # erst hier: paket.py importiert daten.py
    for f in paket.pruefe_alle(paket.eintrags_ids(disziplinen), set(videos)):
        melde(f)
    stand = datenstand()
    (ausgabe / "stand.lua").write_text(
        "-- erzeugt von tools/daten.py aus STAND, nicht von Hand bearbeiten\nreturn " + lua(stand) + "\n",
        encoding="utf-8")
    glossar_app = glossar(ids)
    englisch(disziplinen, glossar_app)
    app = {"format": FORMAT, "stand": stand, "disziplinen": disziplinen, "videos": videos,
           "glossar": glossar_app}
    (ausgabe / "mitori-daten.json").write_text(json.dumps(app, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (ausgabe / "fehlende-kanji.txt").write_text(
        "# Namen ohne Kanji (Schlüssel fehlt in daten/begriffe.yaml bzw. daten/daitoryu-begriffe.yaml)\n"
        + "".join(f"{k}\n" for k in sorted(fehlend)), encoding="utf-8")

    techniken = sum(len(d.get("techniken", [])) for d in disziplinen)
    print(f"daten {stand}: {techniken} Techniken, {len(st_app['odachi'])} Ô-dachi-Formen, "
          f"{mit_video} mit Videostelle, {len(fehlend)} Namen ohne Kanji → {ausgabe}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ausgabe", default=str(WURZEL / "build" / "daten"))
    erzeuge(Path(ap.parse_args().ausgabe))
    if fehler:
        print("\n".join(["Fehler in den Daten:"] + [f"  {f}" for f in fehler]), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
