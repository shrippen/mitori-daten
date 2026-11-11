"""Checks of tools/paket.py: validating Lernpakete, their content JSON, the draft from subtitles."""
import copy
import json
import shutil
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
    "Untertitel keine Liste": (lambda d: d["videos"][0].update(untertitel="a.srt"), "untertitel ist keine nichtleere Liste"),
    "Untertitel leer": (lambda d: d["videos"][0].update(untertitel=[]), "untertitel ist keine nichtleere Liste"),
    "Untertitel kein Eintrag": (lambda d: d["videos"][0].update(untertitel=["a.srt"]), "kein Eintrag mit Feldern"),
    "Untertitel ohne Sprache": (lambda d: d["videos"][0].update(untertitel=[{"datei": "a.srt"}]), "sprache fehlt"),
    "Untertitel ohne Datei": (lambda d: d["videos"][0].update(untertitel=[{"sprache": "en"}]), "datei fehlt"),
    "Untertitel Feld": (lambda d: d["videos"][0].update(untertitel=[{"datei": "a.srt", "sprache": "en", "x": 1}]),
                        "unbekanntes Feld x"),
    "Untertitel Sprache lang": (lambda d: d["videos"][0].update(untertitel=[{"datei": "a.srt", "sprache": "eng"}]),
                                "sprache aus zwei Kleinbuchstaben"),
    "Untertitel Sprache gross": (lambda d: d["videos"][0].update(untertitel=[{"datei": "a.srt", "sprache": "EN"}]),
                                 "sprache aus zwei Kleinbuchstaben"),
    "Untertitel Sprache doppelt": (lambda d: d["videos"][0].update(
        untertitel=[{"datei": "a.srt", "sprache": "en"}, {"datei": "b.srt", "sprache": "en"}]), "sprache en steht doppelt"),
    "Untertitel absolut": (lambda d: d["videos"][0].update(untertitel=[{"datei": "/a.srt", "sprache": "en"}]),
                           "datei nur relativ"),
    "Untertitel mit ..": (lambda d: d["videos"][0].update(untertitel=[{"datei": "../a.srt", "sprache": "en"}]),
                          "datei nur relativ"),
    "wie unbekannt": (lambda d: d["abschnitte"][0]["techniken"][1].update(wie=["aikido/gibt-es-nicht"]), "unbekannte Id"),
    "wie doppelt": (lambda d: d["abschnitte"][0]["techniken"][0].update(wie=d["abschnitte"][0]["techniken"][0]["wie"] * 2),
                    "wie aikido/kyu-grade/x/k5/irimi-nage-2 steht doppelt"),
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


# ── Vorschau ──

ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fehlt")


def vorschau_paket(pakete, tmp_path, monkeypatch):
    """Ein Testvideo (10 s) und ein Paket mit zwei Techniken, eine kürzer als 2 s."""
    videos = tmp_path / "videos"
    videos.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=10:size=640x360:rate=10",
                    str(videos / "v.mp4")], check=True)
    d = copy.deepcopy(GUT)
    d["videos"][0]["datei"] = "v.mp4"
    d["abschnitte"][0]["techniken"][0].update(von=2.0, bis=8.0, pruefen=True)
    d["abschnitte"][0]["techniken"][1].update(von=8.5, bis=9.0)
    schreibe(pakete, "p", d)
    monkeypatch.setattr(paket, "GEHEIM", tmp_path / "geheim")
    return videos


def test_bild_zeiten_begrenzt():
    assert paket.bild_zeiten({"von": 2.0, "bis": 8.0}) == [3.0, 5.0, 7.0]
    assert paket.bild_zeiten({"von": 8.5, "bis": 9.0}) == [8.5, 8.75, 9.0]


@ffmpeg
def test_vorschau_schreibt_bilder_und_seite(pakete, tmp_path, monkeypatch):
    ziel = paket.vorschau("p", vorschau_paket(pakete, tmp_path, monkeypatch))
    assert ziel == tmp_path / "geheim" / "arbeit" / "p" / "vorschau"
    assert sorted(f.name for f in ziel.glob("*.jpg")) == [
        "shomen-uchi-irimi-nage-1-3000.jpg", "shomen-uchi-irimi-nage-2-5000.jpg",
        "shomen-uchi-irimi-nage-3-7000.jpg", "zweite-1-8500.jpg", "zweite-2-8750.jpg", "zweite-3-9000.jpg"]
    seite = (ziel / "index.html").read_text(encoding="utf-8")
    for teil in ("<h2>Grund</h2>", "Irimi-nage", "Shomen-uchi", "0:02–0:08", "pruefen",
                 'src="shomen-uchi-irimi-nage-1-3000.jpg"'):
        assert teil in seite
    assert "http" not in seite.replace("<!doctype html>", "")


@ffmpeg
def test_vorschau_zweiter_lauf_holt_nur_neues(pakete, tmp_path, monkeypatch):
    videos = vorschau_paket(pakete, tmp_path, monkeypatch)
    ziel = paket.vorschau("p", videos)
    bleibt = ziel / "zweite-1-8500.jpg"
    stempel = bleibt.stat().st_mtime_ns

    d = yaml.safe_load((pakete / "p.yaml").read_text(encoding="utf-8"))
    d["abschnitte"][0]["techniken"][0]["bis"] = 6.0
    schreibe(pakete, "p", d)
    paket.vorschau("p", videos)

    assert bleibt.stat().st_mtime_ns == stempel
    assert not (ziel / "shomen-uchi-irimi-nage-3-7000.jpg").exists()
    assert (ziel / "shomen-uchi-irimi-nage-3-5000.jpg").exists()


@ffmpeg
def test_cli_vorschau(pakete, tmp_path, monkeypatch):
    videos = vorschau_paket(pakete, tmp_path, monkeypatch)
    env = {**__import__("os").environ, "MITORI_PAKETE": str(pakete), "MITORI_BUNDLE_GEHEIM": str(tmp_path / "geheim")}
    r = subprocess.run([sys.executable, str(WURZEL / "tools" / "paket.py"), "vorschau", "p", "--videos", str(videos)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith("arbeit/p/vorschau/index.html")


def test_vorschau_ohne_ffmpeg(pakete, monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(SystemExit) as e:
        paket.befehl_vorschau(type("A", (), {"id": "p", "videos": None})())
    assert "ffmpeg" in str(e.value.code)


@ffmpeg
def test_vorschau_nie_in_ein_repo(pakete, tmp_path, monkeypatch):
    """Standbilder sind Videoinhalt: Liegt GEHEIM in einem Git-Repo, schreibt die Vorschau nichts."""
    videos = vorschau_paket(pakete, tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(paket, "GEHEIM", repo / "geheim")
    with pytest.raises(SystemExit, match="Git-Repo"):
        paket.vorschau("p", videos)
    assert not (repo / "geheim" / "arbeit").exists()


@ffmpeg
def test_vorschau_bleibt_in_ihrem_ordner(pakete, tmp_path, monkeypatch):
    """Eine Technik-Id aus einem ungeprüften Entwurf wird kein Pfad außerhalb des Vorschau-Ordners."""
    videos = vorschau_paket(pakete, tmp_path, monkeypatch)
    d = yaml.safe_load((pakete / "p.yaml").read_text(encoding="utf-8"))
    d["abschnitte"][0]["techniken"][0]["id"] = "../../../flucht"
    schreibe(pakete, "p", d)
    with pytest.raises(SystemExit, match="flucht"):
        paket.vorschau("p", videos)
    assert not list(tmp_path.rglob("flucht*"))


def test_gute_untertitel(pakete):
    d = geaendert(lambda d: d["videos"][0].update(
        untertitel=[{"datei": "S/V1.srt", "sprache": "en"}, {"datei": "S/V1.de.srt", "sprache": "de"}]))
    schreibe(pakete, "shirakawa-1", d)
    assert fehler() == []


def test_webvtt_bleibt():
    vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.500\nHallo\n"
    assert paket.webvtt(vtt) == vtt
    assert paket.webvtt("\ufeff" + vtt.replace("\n", "\r\n")) == vtt


def test_srt_wird_webvtt():
    srt = "1\r\n00:00:01,000 --> 00:00:02,500\r\nHallo, Welt\r\nzweite Zeile\r\n\r\n2\r\n00:01:03,250 --> 00:01:04,000\r\nEnde\r\n"
    assert paket.webvtt(srt) == ("WEBVTT\n\n00:00:01.000 --> 00:00:02.500\nHallo, Welt\nzweite Zeile\n\n"
                                 "00:01:03.250 --> 00:01:04.000\nEnde\n")
