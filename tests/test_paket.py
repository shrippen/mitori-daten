"""Checks of tools/paket.py: validating Lernpakete, their content JSON, the draft from subtitles."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "tools"))

import paket  # noqa: E402

PROGRAMM = {"aikido/kyu-grade/x/k5/irimi-nage-2"}
PRUEFUNG = {"aikido/k5"}

GUT = {
    "titel": "Shirakawa", "titel_en": "Shirakawa EN", "sparte": "aikido", "text": "Beschreibung",
    "videos": [{"id": "shirakawa-1/v1", "datei": "S/V1.mp4", "titel": "Vol. 1",
                "beschnitt": {"hoehe": 1080, "y": 0, "h": 1080, "verhaeltnis": 1.7778}}],
    "abschnitte": [{"titel": "Grund", "titel_en": "Basic", "techniken": [
        {"id": "shomen-uchi-irimi-nage", "name": "Irimi-nage", "angriff": "Shomen-uchi", "angriff_en": "Overhead strike",
         "zusatz": "ura", "text": "Text", "text_en": "Text EN", "wie": ["aikido/kyu-grade/x/k5/irimi-nage-2"],
         "video": "shirakawa-1/v1", "von": 129.0, "bis": 152.6},
        {"id": "zweite", "name": "Unbekannt-waza", "video": "shirakawa-1/v1", "von": 152.6, "bis": 170}]}],
}


@pytest.fixture
def pakete(tmp_path, monkeypatch):
    ordner = tmp_path / "pakete"
    ordner.mkdir()
    monkeypatch.setattr(paket, "PAKETE", ordner)
    return ordner


def schreibe(ordner, pid, d):
    (ordner / f"{pid}.yaml").write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")


def fehler():
    return paket.pruefe_alle(PROGRAMM, PRUEFUNG)


def geaendert(aendere):
    d = copy.deepcopy(GUT)
    aendere(d)
    return d


def test_gutes_paket(pakete):
    schreibe(pakete, "shirakawa-1", GUT)
    assert fehler() == []


def test_ohne_pakete_ist_gut(pakete):
    assert fehler() == []


FALSCH = {
    "pflichtfeld": (lambda d: d.pop("titel"), "titel fehlt"),
    "keine Videos": (lambda d: d.update(videos=[]), "videos fehlt oder ist leer"),
    "keine Abschnitte": (lambda d: d.update(abschnitte=[]), "abschnitte fehlt oder ist leer"),
    "Sparte": (lambda d: d.update(sparte="judo"), "Sparte judo"),
    "unbekanntes Feld": (lambda d: d.update(farbe="rot"), "unbekanntes Feld farbe"),
    "en ohne Feld": (lambda d: (d.pop("text"), d.update(text_en="x")), "text_en ohne text"),
    "en gleich": (lambda d: d.update(titel_en=d["titel"]), "titel_en gleich titel"),
    "en beim Abschnitt ohne Feld": (lambda d: d["abschnitte"][0].update(text_en="x"),
                                    "text_en ohne text"),
    "Technik ohne Video": (lambda d: d["abschnitte"][0]["techniken"][0].update(video="anderes/v9"), "steht nicht in videos"),
    "doppelte Technik": (lambda d: d["abschnitte"][0]["techniken"][1].update(id="shomen-uchi-irimi-nage"), "steht doppelt"),
    "Technik-Id": (lambda d: d["abschnitte"][0]["techniken"][1].update(id="Gross Klein"), "Id nur aus a-z"),
    "von nach bis": (lambda d: d["abschnitte"][0]["techniken"][1].update(von=9, bis=3), "von 9 bis 3"),
    "von negativ": (lambda d: d["abschnitte"][0]["techniken"][1].update(von=-1), "von -1"),
    "wie unbekannt": (lambda d: d["abschnitte"][0]["techniken"][1].update(wie=["aikido/gibt-es-nicht"]), "unbekannte Id"),
    "Video doppelt": (lambda d: d["videos"].append(dict(d["videos"][0])), "steht doppelt"),
    "Video ist Prüfungsvideo": (lambda d: d["videos"][0].update(id="aikido/k5"), "Prüfungsvideo"),
    "Video-Id": (lambda d: d["videos"][0].update(id="Shirakawa"), "Id nur aus a-z"),
    "datei absolut": (lambda d: d["videos"][0].update(datei="/etc/passwd"), "datei nur relativ"),
    "datei hinauf": (lambda d: d["videos"][0].update(datei="../x.mp4"), "datei nur relativ"),
}


@pytest.mark.parametrize("name", FALSCH)
def test_fehler(pakete, name):
    aendere, soll = FALSCH[name]
    schreibe(pakete, "shirakawa-1", geaendert(aendere))
    assert any(soll in f for f in fehler()), fehler()


def test_id_ist_der_dateiname(pakete):
    schreibe(pakete, "Gross", GUT)
    assert any("Dateiname" in f for f in fehler())


def test_id_wie_ein_bundle(pakete):
    schreibe(pakete, "aikido-kyu", GUT)
    assert any("Bundle" in f for f in fehler())


def test_videoschluessel_eindeutig_ueber_pakete(pakete):
    schreibe(pakete, "a", GUT)
    schreibe(pakete, "b", GUT)
    f = fehler()
    assert any("b, Video shirakawa-1/v1: Id gehört schon dem Paket a" in x for x in f), f


def test_alle_fehler_zusammen(pakete):
    schreibe(pakete, "shirakawa-1", geaendert(lambda d: (d.update(sparte="judo"), d.pop("titel"))))
    assert len(fehler()) >= 2


def test_kaputtes_yaml(pakete):
    (pakete / "x.yaml").write_text("a: [", encoding="utf-8")
    assert any("kein gültiges YAML" in f for f in fehler())


def test_inhalt(pakete):
    schreibe(pakete, "shirakawa-1", GUT)
    j = paket.inhalt("shirakawa-1")
    assert j["format"] == paket.FORMAT == 1
    assert j["id"] == "shirakawa-1" and j["titel_en"] == "Shirakawa EN" and j["text"] == "Beschreibung"
    assert j["videos"] == [{"id": "shirakawa-1/v1", "beschnitt": GUT["videos"][0]["beschnitt"]} | {"titel": "Vol. 1"}]
    assert "datei" not in j["videos"][0]
    a = j["abschnitte"][0]
    assert a["titel"] == "Grund" and a["titel_en"] == "Basic" and "text" not in a
    t = a["techniken"][0]
    assert t["id"] == "lern/shirakawa-1/shomen-uchi-irimi-nage"
    assert t["jp"] == "入身投げ"
    assert t["angriff"] == {"name": "Shomen-uchi", "name_en": "Overhead strike", "jp": "正面打ち"}
    assert t["text_en"] == "Text EN" and "name_en" not in t and "zusatz_en" not in t
    assert (t["von"], t["bis"], t["video"]) == (129.0, 152.6, "shirakawa-1/v1")
    assert t["wie"] == ["aikido/kyu-grade/x/k5/irimi-nage-2"]
    unbekannt = a["techniken"][1]
    assert "jp" not in unbekannt and "angriff" not in unbekannt
    json.dumps(j, ensure_ascii=False)


def test_inhalt_ohne_beschnitt_und_daitoryu(pakete):
    d = geaendert(lambda d: (d.update(sparte="daitoryu"), d["videos"][0].pop("beschnitt")))
    schreibe(pakete, "x", d)
    assert "beschnitt" not in paket.inhalt("x")["videos"][0]


def test_entwurf_ist_gueltig_und_ungebaut(pakete):
    d = copy.deepcopy(GUT)
    d["abschnitte"][0]["techniken"][1]["pruefen"] = True
    schreibe(pakete, "x", d)
    assert fehler() == []
    assert paket.ist_entwurf(yaml.safe_load((pakete / "x.yaml").read_text(encoding="utf-8")))
    assert not paket.ist_entwurf(GUT)


WEBVTT = """WEBVTT
Kind: captions
Language: de

NOTE ein Kommentar
der weitergeht

00:00:01.000 --> 00:00:04.000 align:start position:0%
Hallo und herzlich willkommen
zu diesem Lehrgang, heute geht es los.

00:00:05.500 --> 00:00:07.000
Shomen-uchi <c>Irimi-nage</c>

2
00:00:07.000 --> 00:00:09.000
Shomen-uchi <c>Irimi-nage</c>

00:12.250 --> 00:15.000
und dann dreht er sich.

01:01:02,500 --> 01:01:10,000
Katate-dori Shiho-nage

01:01:10,000 --> 01:01:12,250
Das war es.
"""


def test_untertitel_beide_zeitformen():
    z = paket.untertitel(WEBVTT)
    assert [t for _, _, t in z] == ["Hallo und herzlich willkommen zu diesem Lehrgang, heute geht es los.",
                                    "Shomen-uchi Irimi-nage", "Shomen-uchi Irimi-nage", "und dann dreht er sich.",
                                    "Katate-dori Shiho-nage", "Das war es."]
    assert z[0][:2] == (1.0, 4.0)
    assert z[3][:2] == (12.25, 15.0)
    assert z[4][:2] == (3662.5, 3670.0)


def test_entwurf_aus_untertiteln():
    d = yaml.safe_load(paket.entwurf(paket.untertitel(WEBVTT), "shirakawa-1/v1", "shirakawa-1"))
    t = d["abschnitte"][0]["techniken"]
    assert [x["name"] for x in t] == ["Shomen-uchi Irimi-nage", "Katate-dori Shiho-nage"]
    assert [x["id"] for x in t] == ["shomen-uchi-irimi-nage", "katate-dori-shiho-nage"]
    assert (t[0]["von"], t[0]["bis"]) == (5.5, 3662.5)
    assert (t[1]["von"], t[1]["bis"]) == (3662.5, 3672.25)       # das Ende des letzten Untertitels
    assert all(x["pruefen"] is True and x["video"] == "shirakawa-1/v1" for x in t)


def test_entwurf_besteht_die_pruefung(pakete):
    text = paket.entwurf(paket.untertitel(WEBVTT), "shirakawa-1/v1", "shirakawa-1")
    (pakete / "shirakawa-1.yaml").write_text(text, encoding="utf-8")
    assert fehler() == []


def test_entwurf_srt_und_doppelte_namen():
    """Dieselbe Zeile gleich noch einmal zählt einmal; kehrt der Name später wieder, bekommt er eine Nummer."""
    srt = ("1\n00:00:01,000 --> 00:00:02,000\nIkkyo\n\n2\n00:00:02,000 --> 00:00:03,000\nIkkyo\n\n"
           "3\n00:00:03,000 --> 00:00:04,000\nBlah blah.\n\n4\n00:00:05,000 --> 00:00:06,000\nIkkyo\n")
    t = yaml.safe_load(paket.entwurf(paket.untertitel(srt), "a/b"))["abschnitte"][0]["techniken"]
    assert [x["id"] for x in t] == ["ikkyo", "ikkyo-2"]


def test_cli_entwurf_und_inhalt(pakete, tmp_path):
    vtt = tmp_path / "u.srt"
    vtt.write_text(WEBVTT, encoding="utf-8")
    r = subprocess.run([sys.executable, str(WURZEL / "tools" / "paket.py"), "entwurf", str(vtt), "--video", "a/b"],
                       capture_output=True, text=True, check=True)
    assert "pruefen: true" in r.stdout


def test_echtes_repo_besteht():
    r = subprocess.run([sys.executable, str(WURZEL / "tools" / "paket.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
