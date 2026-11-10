"""Checks of tools/bundle.py: codes, wrapping the key, encrypting files (the app reads the same)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

nacl = pytest.importorskip("nacl", reason="PyNaCl (python-pynacl) needed for tools/bundle.py")

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "tools"))
import paket  # noqa: E402  (dieselbe Instanz wie in bundle.py)

spec = importlib.util.spec_from_file_location("bundle", WURZEL / "tools" / "bundle.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)

KLEIN = {"t": 1, "m": 8}        # Argon2id small for tests (the tool uses t=3, 64 MiB)


def test_code_hat_pruefzeichen():
    for _ in range(200):
        code = bundle.neuer_code()
        assert len(code) == 20
        assert bundle.normalisiert(code) == code
        assert bundle.normalisiert(bundle.gruppiert(code).lower()) == code
        # Ein falsches Zeichen fällt auf.
        i = 7
        falsch = code[:i] + bundle.ALPHABET[(bundle.ALPHABET.index(code[i]) + 1) % 32] + code[i + 1:]
        assert bundle.normalisiert(falsch) is None


def test_code_vertauscht_faellt_auf():
    code = "7KQ2MX9HDV3TAPRWE6Y"
    code += bundle.pruefzeichen(code)
    vertauscht = code[1] + code[0] + code[2:]
    assert bundle.normalisiert(vertauscht) is None


def test_eingabe_nachsichtig():
    code = "0123456789ABCDEFGHJ"
    code += bundle.pruefzeichen(code)
    eingabe = " o" + "i" + "23-4567 89abc defgh j" + code[-1].lower()     # O → 0, I → 1, Bindestriche, Leerzeichen
    assert bundle.normalisiert(eingabe) == code
    assert bundle.normalisiert("0l" + code[2:]) == code                    # L → 1
    assert bundle.normalisiert("zu kurz") is None
    assert bundle.normalisiert("U" * 20) is None


def test_kennung_verraet_den_code_nicht():
    code = bundle.neuer_code()
    k = bundle.kennung(code)
    assert len(k) == 32 and code not in k
    assert k == bundle.kennung(code)


def test_schluessel_umhuellt_und_ausgepackt():
    code = bundle.neuer_code()
    k = os.urandom(32)
    e = bundle.umhuellt(code, "aikido-kyu", k, **KLEIN)
    assert bundle.ausgepackt(code, e) == k
    falsch = bundle.neuer_code()
    with pytest.raises(Exception):
        bundle.ausgepackt(falsch, e)
    anderes = dict(e, bundle="aikido-dan")      # die AD bindet den Schlüssel an sein Bundle
    with pytest.raises(Exception):
        bundle.ausgepackt(code, anderes)


@pytest.mark.parametrize("groesse", [0, 5, bundle.BLOCK, bundle.BLOCK + 1, 2 * bundle.BLOCK + 17])
def test_datei_hin_und_zurueck(tmp_path, groesse):
    klar = tmp_path / "v.mkv"
    klar.write_bytes(os.urandom(groesse))
    k = os.urandom(32)
    g, sha, kg = bundle.verschluesselt(klar, tmp_path / "v.mvb", k)
    assert kg == groesse
    bloecke = max(1, -(-groesse // bundle.BLOCK))
    assert g == 8 + 16 + groesse + 16 * bloecke
    bundle.entschluesselt(tmp_path / "v.mvb", tmp_path / "zurueck.mkv", k)
    assert (tmp_path / "zurueck.mkv").read_bytes() == klar.read_bytes()


def test_abgeschnitten_faellt_auf(tmp_path):
    klar = tmp_path / "v.mkv"
    klar.write_bytes(os.urandom(2 * bundle.BLOCK + 5))
    k = os.urandom(32)
    bundle.verschluesselt(klar, tmp_path / "v.mvb", k)
    roh = (tmp_path / "v.mvb").read_bytes()
    # Ohne den letzten Block: der vorletzte gilt jetzt als letzter, seine AD passt nicht.
    (tmp_path / "kurz.mvb").write_bytes(roh[:8 + 16 + 2 * (bundle.BLOCK + 16)])
    with pytest.raises(Exception):
        bundle.entschluesselt(tmp_path / "kurz.mvb", tmp_path / "x", k)


def test_bundles_kennen_ihre_videos():
    import json
    import subprocess
    import sys
    subprocess.run([sys.executable, str(WURZEL / "tools" / "daten.py")], check=True, capture_output=True)
    videos = json.loads((WURZEL / "build" / "daten" / "mitori-daten.json").read_text(encoding="utf-8"))["videos"]
    alle = [v for b in bundle.definitionen().values() for v in b["videos"]]
    assert sorted(alle) == sorted(videos), "jedes Video in genau einem Bundle"


def test_ids_sind_ordnernamen():
    """Die App nimmt nur Ids aus Kleinbuchstaben, Ziffern und Bindestrichen (BundleShelf::validId)."""
    assert all(bundle.ID.fullmatch(i) for i in bundle.definitionen())
    for falsch in ("..", "/tmp", "a/b", "Aikido", ""):
        assert not bundle.ID.fullmatch(falsch)


# ── Das Werkzeug für die Lizenz-Downloads ──

@pytest.fixture(autouse=True)
def kein_netz(monkeypatch):
    """Kein Test spricht mit dem echten Server."""
    monkeypatch.setattr(bundle.urllib.request, "urlopen", lambda *a, **k: pytest.fail("Netz im Test"))


@pytest.fixture
def geheim(tmp_path, monkeypatch):
    ordner = tmp_path / "geheim"
    monkeypatch.setattr(bundle, "GEHEIM", ordner)
    return ordner


def test_geheim_nicht_im_repo(tmp_path, monkeypatch):
    """Schlüssel, Codes und Videos kommen nie in ein Git-Repo: der Ordner darin wird abgelehnt."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(bundle, "GEHEIM", repo / "unter" / "geheim")
    with pytest.raises(SystemExit, match="Git"):
        bundle.geheim_pruefen()
    monkeypatch.setattr(bundle, "GEHEIM", tmp_path / "frei")
    bundle.geheim_pruefen()
    assert (tmp_path / "frei").stat().st_mode & 0o077 == 0, "nur der Besitzer"


def test_code_mit_empfaenger(geheim):
    """Die Lizenz: wer welchen Code bekam, steht nur in der privaten CSV, nie im Manifest."""
    args = type("A", (), {"bundle": "aikido-kyu", "anzahl": 2, "fuer": "Dojo Köln"})
    bundle.befehl_codes(args)
    zeilen = (geheim / "codes" / "aikido-kyu.csv").read_text(encoding="utf-8").splitlines()
    assert zeilen[0] == "code,datum,kennung,fuer"
    assert len(zeilen) == 3 and all(z.endswith(",Dojo Köln") for z in zeilen[1:])
    assert "Dojo" not in (geheim / "manifest.json").read_text(encoding="utf-8")


def test_upload_nur_verschluesselt(tmp_path):
    """Vor dem Upload: eine Datei ohne die Magie (ein Klartext-Video) stoppt alles."""
    klar = tmp_path / "x.mvb"
    klar.write_bytes(b"\x1aE\xdf\xa3 mkv")
    with pytest.raises(SystemExit, match="verschlüsselt"):
        bundle.verschluesselt_pruefen(klar)
    roh = tmp_path / "y.mvb"
    bundle.verschluesselt(klar, roh, b"k" * 32)
    bundle.verschluesselt_pruefen(roh)


def test_upload_braucht_zustimmung(geheim):
    args = type("A", (), {"nur_manifest": False, "verband_stimmt_zu": False, "probe": False})
    with pytest.raises(SystemExit, match="verband-stimmt-zu"):
        bundle.befehl_hochladen(args)


def _gebaut(geheim, tmp_path):
    """Ein gebautes Bundle ohne ffmpeg: eine kleine Datei, verschlüsselt, im Manifest."""
    quelle = tmp_path / "klar.bin"
    quelle.write_bytes(b"inhalt" * 500000)
    aus = geheim / "aus" / "aikido-kyu" / "1"
    aus.mkdir(parents=True)
    k = bundle.schluessel("aikido-kyu")
    g, sha, klar = bundle.verschluesselt(quelle, aus / "aikido-k5.mvb", k)
    m = bundle.manifest_lesen()
    m["bundles"] = [{"id": "aikido-kyu", "version": 1, "titel": "t", "hinweis": None,
                     "videos": [{"video": "aikido/k5", "datei": "aikido-k5.mvb", "groesse": g, "sha256": sha,
                                 "klar": klar, "beschnitten": False,
                                 "kapitel": bundle.schnittpunkte("aikido/k5")}]}]
    bundle.manifest_schreiben(m)
    return aus / "aikido-k5.mvb"


def test_verifizieren(geheim, tmp_path, monkeypatch):
    """Verifizieren findet eine beschädigte Datei und eine falsche Größe; eine heile geht durch."""
    datei = _gebaut(geheim, tmp_path)
    monkeypatch.setattr(bundle, "_laenge_fehler", lambda *a: [])   # kein echtes Video
    assert bundle.verifiziert("aikido-kyu") == []
    roh = bytearray(datei.read_bytes())
    roh[-5] ^= 1
    datei.write_bytes(roh)
    assert any("aikido-k5.mvb" in f for f in bundle.verifiziert("aikido-kyu"))
    datei.unlink()
    assert any("fehlt" in f for f in bundle.verifiziert("aikido-kyu"))


def test_stand(geheim, tmp_path):
    """Die Übersicht je Bundle: gebaut oder nicht, Version, Größe, Codes."""
    _gebaut(geheim, tmp_path)
    args = type("A", (), {"bundle": "aikido-kyu", "anzahl": 1, "fuer": ""})
    bundle.befehl_codes(args)
    zeilen = bundle.stand_zeilen()
    aikido = next(z for z in zeilen if z.startswith("aikido-kyu"))
    assert "Version 1" in aikido and "1 Codes" in aikido
    assert any(z.startswith("daitoryu-kyu") and "nicht gebaut" in z for z in zeilen)


# ── Abbrüche und Testbauten ──

ffmpeg_da = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fehlt")


def _video(pfad, sekunden, *zusatz):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=64x48:rate=25:d={sekunden}",
                    "-c:v", "libx264", "-preset", "ultrafast", *zusatz, str(pfad)], check=True)


def test_abbruch_laesst_keine_fertige_datei(tmp_path, monkeypatch):
    """Bricht die Kodierung ab, liegt unter dem Zielnamen nichts: der nächste Lauf kodiert neu."""
    ziel = tmp_path / "a.mkv"

    def bricht_ab(befehl, check):
        Path(befehl[-1]).write_bytes(b"halb")
        raise KeyboardInterrupt
    monkeypatch.setattr(bundle.subprocess, "run", bricht_ab)
    with pytest.raises(KeyboardInterrupt):
        bundle.beschnitten(tmp_path / "q.mkv", ziel, {"h": 480, "hoehe": 480, "y": 0})
    assert not ziel.exists()

    monkeypatch.setattr(bundle.subprocess, "run", lambda befehl, check: Path(befehl[-1]).write_bytes(b"ganz"))
    bundle.beschnitten(tmp_path / "q.mkv", ziel, {"h": 480, "hoehe": 480, "y": 0})
    assert ziel.read_bytes() == b"ganz"
    assert [p.name for p in tmp_path.iterdir()] == ["a.mkv"]


@ffmpeg_da
def test_bilder_zaehlt_wirklich(tmp_path):
    """Die Kopfdaten lügen bei einem Rest: die Länge kommt aus den gezählten Bildern."""
    voll = tmp_path / "voll.mkv"
    _video(voll, 8)
    assert bundle.bilder(voll) == 200
    rest = tmp_path / "rest.mkv"
    rest.write_bytes(voll.read_bytes()[:voll.stat().st_size // 2])
    assert 0 < bundle.bilder(rest) < 200


def _mit_bildern(geheim, tmp_path, monkeypatch, zahl):
    datei = _gebaut(geheim, tmp_path)
    m = bundle.manifest_lesen()
    m["bundles"][0]["videos"][0]["bilder"] = 200
    bundle.manifest_schreiben(m)
    monkeypatch.setattr(bundle, "bilder", lambda pfad: zahl)
    return datei


def test_verifizieren_findet_kurzes_video(geheim, tmp_path, monkeypatch):
    _mit_bildern(geheim, tmp_path, monkeypatch, 180)
    assert any("180" in f and "200" in f for f in bundle.verifiziert("aikido-kyu"))


def test_verifizieren_mit_passender_laenge(geheim, tmp_path, monkeypatch):
    _mit_bildern(geheim, tmp_path, monkeypatch, 200)
    assert bundle.verifiziert("aikido-kyu") == []


def test_verifizieren_ohne_bundles_ist_ein_fehler(geheim):
    """„0 Bundles in Ordnung“ bei falschem Ordner wäre ein falsches Ja."""
    with pytest.raises(SystemExit, match="keine"):
        bundle.befehl_verifizieren(type("A", (), {"bundle": None}))


def test_pruefen_legt_keine_schluessel_an(geheim, tmp_path, monkeypatch):
    """Ein fehlender Schlüssel bleibt fehlend: sonst umhüllen spätere Codes den falschen."""
    _gebaut(geheim, tmp_path)
    (geheim / "schluessel" / "aikido-kyu.key").unlink()
    assert any("Schlüssel" in f for f in bundle.verifiziert("aikido-kyu"))
    assert not (geheim / "schluessel" / "aikido-kyu.key").exists()


def test_alle_ersetzt_testbauten(geheim, tmp_path, monkeypatch):
    """Ein Testbau (--ohne-kodieren) zählt für den echten Lauf nicht als gebaut."""
    _gebaut(geheim, tmp_path)
    gebaut = []
    monkeypatch.setattr(bundle, "befehl_build", lambda args: gebaut.append(args.bundle))
    bundle.befehl_alle(type("A", (), {"neu": False, "ohne_kodieren": False}))
    assert "aikido-kyu" in gebaut
    gebaut.clear()
    bundle.befehl_alle(type("A", (), {"neu": False, "ohne_kodieren": True}))
    assert "aikido-kyu" not in gebaut


def test_stand_nennt_testbauten(geheim, tmp_path):
    _gebaut(geheim, tmp_path)
    assert any(z.startswith("aikido-kyu") and "Test" in z for z in bundle.stand_zeilen())


def test_testbau_wird_nicht_hochgeladen(geheim, tmp_path, monkeypatch):
    _gebaut(geheim, tmp_path)
    monkeypatch.setattr(bundle, "_laenge_fehler", lambda *a: [])
    args = type("A", (), {"nur_manifest": False, "verband_stimmt_zu": True, "probe": False})
    with pytest.raises(SystemExit, match="Testbau"):
        bundle.befehl_hochladen(args)


def _echt(geheim):
    m = bundle.manifest_lesen()
    m["bundles"][0]["videos"][0]["beschnitten"] = True
    bundle.manifest_schreiben(m)


def test_upload_nur_nach_pruefung(geheim, tmp_path, monkeypatch):
    """Eine beschädigte Datei geht nicht hinaus, vor dem ersten Request."""
    datei = _gebaut(geheim, tmp_path)
    _echt(geheim)
    (geheim / "gitea-token").write_text("t")
    monkeypatch.setattr(bundle, "_laenge_fehler", lambda *a: [])
    monkeypatch.setattr(bundle, "hochladen", lambda *a, **k: pytest.fail("nichts darf hinaus"))
    roh = bytearray(datei.read_bytes())
    roh[-5] ^= 1
    datei.write_bytes(roh)
    args = type("A", (), {"nur_manifest": False, "verband_stimmt_zu": True, "probe": False})
    with pytest.raises(SystemExit, match="nichts wird hochgeladen"):
        bundle.befehl_hochladen(args)


def test_probe_nennt_fehlende_dateien(geheim, tmp_path, capsys):
    datei = _gebaut(geheim, tmp_path)
    datei.unlink()
    bundle.befehl_hochladen(type("A", (), {"nur_manifest": False, "verband_stimmt_zu": False, "probe": True}))
    assert "FEHLT" in capsys.readouterr().out


def test_arbeitsdatei_haengt_am_beschnitt():
    """Ein geänderter Beschnitt nimmt nicht die alte Kodierung."""
    a = bundle.arbeitsname("aikido/k5", {"h": 480, "y": 100})
    assert a != bundle.arbeitsname("aikido/k5", {"h": 480, "y": 96})
    assert a.endswith(".mkv") and "/" not in a


def test_alle_hat_keine_version():
    """Eine Version für alle würde Bundles zurücksetzen: die App sähe das Update nie."""
    quelle = (Path(bundle.__file__)).read_text(encoding="utf-8")
    teil = quelle[quelle.index('sub.add_parser("alle")'):quelle.index('sub.add_parser("verifizieren")')]
    assert "--version" not in teil


def _kodierung(tmp_path, monkeypatch, ist, klar_ende, quelle_ende):
    klar = tmp_path / "k.mkv"
    klar.write_bytes(b"x")
    monkeypatch.setattr(bundle, "bilder", lambda p: ist)
    monkeypatch.setattr(bundle, "laufzeit", lambda p: klar_ende if p == klar else quelle_ende)
    return klar


def test_kurze_kodierung_stoppt_ohne_zu_loeschen(tmp_path, monkeypatch):
    """Ein Rest (8 von 20 s) geht nicht ins Bundle; gelöscht wird nichts, die Meldung nennt die Datei."""
    klar = _kodierung(tmp_path, monkeypatch, 199, 8.0, 20.0)
    with pytest.raises(SystemExit, match="k.mkv"):
        bundle.bilder_der_kodierung("v", tmp_path / "q.mkv", klar)
    assert klar.exists()
    assert bundle.bilder_der_kodierung("v", tmp_path / "q.mkv", klar, laenge_egal=True) == 199


def test_knapp_kurz_ist_ein_hinweis(tmp_path, monkeypatch, capsys):
    klar = _kodierung(tmp_path, monkeypatch, 460, 18.4, 20.0)
    assert bundle.bilder_der_kodierung("v", tmp_path / "q.mkv", klar) == 460
    assert "Achtung" in capsys.readouterr().err


def test_ganze_kodierung_still(tmp_path, monkeypatch, capsys):
    klar = _kodierung(tmp_path, monkeypatch, 500, 19.96, 20.0)
    assert bundle.bilder_der_kodierung("v", tmp_path / "q.mkv", klar) == 500
    assert capsys.readouterr().err == ""


def test_fehlende_quelle_stoppt_ohne_zu_loeschen(tmp_path, monkeypatch):
    klar = _kodierung(tmp_path, monkeypatch, 500, 20.0, None)
    with pytest.raises(SystemExit, match="Quelle"):
        bundle.bilder_der_kodierung("v", tmp_path / "q.mkv", klar)
    assert klar.exists()


def test_unlesbare_kodierung_nennt_die_datei(tmp_path, monkeypatch):
    klar = _kodierung(tmp_path, monkeypatch, 0, None, 20.0)
    with pytest.raises(SystemExit, match="k.mkv"):
        bundle.bilder_der_kodierung("v", tmp_path / "q.mkv", klar)


@ffmpeg_da
def test_laufzeit_nimmt_die_videospur(tmp_path):
    """Längerer Ton täuscht sie nicht (die Kopfdaten schon)."""
    v = tmp_path / "v.mkv"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=25:d=6",
                    "-f", "lavfi", "-i", "sine=d=20", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    str(v)], check=True)
    assert abs(bundle.laufzeit(v) - 6) < 0.2
    assert bundle.laufzeit(tmp_path / "fehlt.mkv") is None


@ffmpeg_da
def test_laufzeit_ab_dem_ersten_bild(tmp_path):
    """Eine Datei, die nicht bei 0 beginnt (ein VOB aus der Titelmitte): die Kodierung beginnt bei 0."""
    v = tmp_path / "v.mkv"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=25:d=6",
                    "-c:v", "libx264", "-preset", "ultrafast", "-output_ts_offset", "600", str(v)], check=True)
    assert abs(bundle.laufzeit(v) - 6) < 0.2


def test_quelle_ohne_zeitmarken_sagt_was_ist(tmp_path, monkeypatch):
    q = tmp_path / "q.h264"
    q.write_bytes(b"x")
    klar = _kodierung(tmp_path, monkeypatch, 500, 20.0, None)
    with pytest.raises(SystemExit, match="laenge-egal"):
        bundle.bilder_der_kodierung("v", q, klar)
    assert klar.exists()


def test_bilder_nimmt_die_erste_zahl(monkeypatch):
    """TS antwortet mit `250\\n\\n250`."""
    monkeypatch.setattr(bundle.shutil, "which", lambda n: "ffprobe")
    monkeypatch.setattr(bundle.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": "250\n\n250\n"}))
    assert bundle.bilder("x.ts") == 250


def test_verifizieren_prueft_den_ordner(tmp_path, monkeypatch):
    """Der Klartext zur Probe entsteht nie in einem Repo."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(bundle, "GEHEIM", repo / "geheim")
    with pytest.raises(SystemExit, match="Git"):
        bundle.verifiziert("aikido-kyu")


def test_upload_ohne_bundles_geht_nicht(geheim, monkeypatch):
    geheim.mkdir()
    (geheim / "gitea-token").write_text("t")
    monkeypatch.setattr(bundle, "hochladen", lambda *a, **k: pytest.fail("nichts darf hinaus"))
    args = type("A", (), {"nur_manifest": False, "verband_stimmt_zu": True, "probe": False})
    with pytest.raises(SystemExit, match="keine Bundles"):
        bundle.befehl_hochladen(args)


def test_upload_ohne_ffprobe_geht_nicht(geheim, tmp_path, monkeypatch):
    _gebaut(geheim, tmp_path)
    _echt(geheim)
    (geheim / "gitea-token").write_text("t")
    monkeypatch.setattr(bundle.shutil, "which", lambda name: None)
    monkeypatch.setattr(bundle, "hochladen", lambda *a, **k: pytest.fail("nichts darf hinaus"))
    args = type("A", (), {"nur_manifest": False, "verband_stimmt_zu": True, "probe": False})
    with pytest.raises(SystemExit, match="ffprobe"):
        bundle.befehl_hochladen(args)


def test_leeres_manifest_geht_nie_hinaus(geheim, monkeypatch):
    """Es nähme auf dem Server alle Codes und Bundles weg."""
    geheim.mkdir()
    (geheim / "gitea-token").write_text("t")
    monkeypatch.setattr(bundle, "hochladen", lambda *a, **k: pytest.fail("nichts darf hinaus"))
    args = type("A", (), {"nur_manifest": True, "verband_stimmt_zu": True, "probe": False})
    with pytest.raises(SystemExit, match="keine Bundles"):
        bundle.befehl_hochladen(args)


def test_nur_manifest_ohne_dateien(geheim, tmp_path, monkeypatch):
    """Eine Sperrung (nur das Manifest) braucht die Videos nicht auf diesem Rechner."""
    datei = _gebaut(geheim, tmp_path)
    _echt(geheim)
    datei.unlink()
    (geheim / "gitea-token").write_text("t")
    (geheim / "video-basis").write_text("https://v.example/m\n")
    monkeypatch.setattr(bundle, "adressen_fehler", lambda *a: [])
    gesendet = []
    monkeypatch.setattr(bundle, "hochladen", lambda *a, **k: gesendet.append(a))
    bundle.befehl_hochladen(type("A", (), {"nur_manifest": True, "verband_stimmt_zu": True, "probe": False}))
    assert len(gesendet) == 1


# ── Auslieferung: Videos über Caddy, Manifest über Gitea, Schnittpunkte im Manifest ──

def _ausliefern(geheim, tmp_path, monkeypatch, ablauf=None):
    """Ein echtes Bundle, Ziel ein Ordner; Gitea und die Adressprüfung sind ersetzt und schreiben `ablauf` mit."""
    datei = _gebaut(geheim, tmp_path)
    _echt(geheim)
    ziel = tmp_path / "server"
    ziel.mkdir()
    (geheim / "gitea-token").write_text("t")
    (geheim / "video-basis").write_text("https://v.example/m/\n")
    (geheim / "video-ziel").write_text(str(ziel))
    monkeypatch.setattr(bundle, "_laenge_fehler", lambda *a: [])
    ablauf = [] if ablauf is None else ablauf

    def manifest(paket, version, name, daten, token, laenge=None):
        ablauf.append(("manifest", json.loads(daten), sorted(p.name for p in (ziel / "aikido-kyu").iterdir())))

    monkeypatch.setattr(bundle, "hochladen", manifest)
    monkeypatch.setattr(bundle, "adressen_fehler", lambda m, basis: ablauf.append(("adressen", basis)) or [])
    return datei, ziel, ablauf


HOCH = type("A", (), {"nur_manifest": False, "verband_stimmt_zu": True, "probe": False})
rsync = pytest.mark.skipif(not shutil.which("rsync") or not shutil.which("ffprobe"), reason="rsync und ffprobe nötig")


@rsync
def test_videos_vor_dem_manifest(geheim, tmp_path, monkeypatch):
    """Erst die Dateien, dann ihre Prüfung, dann das Manifest mit Adresse und Schnittpunkten."""
    datei, ziel, ablauf = _ausliefern(geheim, tmp_path, monkeypatch)
    bundle.befehl_hochladen(HOCH)
    assert (ziel / "aikido-kyu" / "1" / "aikido-k5.mvb").read_bytes() == datei.read_bytes()
    assert [a[0] for a in ablauf] == ["adressen", "manifest"]
    m = ablauf[1][1]
    assert m["format"] == 2 and "basis" not in m
    v = m["bundles"][0]["videos"][0]
    assert v["url"] == "https://v.example/m/aikido-kyu/1/aikido-k5.mvb"
    assert v["kapitel"] == bundle.schnittpunkte("aikido/k5")
    assert "url" not in bundle.manifest_lesen()["bundles"][0]["videos"][0]    # die Adresse hängt am Server


@rsync
def test_alte_version_geht_erst_nach_dem_manifest(geheim, tmp_path, monkeypatch):
    """Auf dem Server bleibt nur die aktuelle Version, aber bis zum neuen Manifest auch die alte."""
    datei, ziel, ablauf = _ausliefern(geheim, tmp_path, monkeypatch)
    alt = ziel / "aikido-kyu" / "0"
    alt.mkdir(parents=True)
    (alt / "alt.mvb").write_bytes(b"alt")
    bundle.befehl_hochladen(HOCH)
    assert ablauf[1][2] == ["0", "1"]
    assert not alt.exists()
    assert (ziel / "aikido-kyu" / "1" / "aikido-k5.mvb").exists()


@rsync
def test_nur_dateien_des_manifests_gehen_hinaus(geheim, tmp_path, monkeypatch):
    """Ein Klartext im selben Ordner bleibt auf dem Rechner."""
    datei, ziel, _ = _ausliefern(geheim, tmp_path, monkeypatch)
    (datei.parent / "klar.mkv").write_bytes(b"klartext")
    (geheim / "aus" / "aikido-kyu" / "klar.mkv").write_bytes(b"klartext")
    bundle.befehl_hochladen(HOCH)
    gefunden = sorted(p.name for p in ziel.rglob("*") if p.is_file())
    assert gefunden == ["aikido-k5.mvb"]


@rsync
def test_falsche_adresse_laesst_das_manifest(geheim, tmp_path, monkeypatch):
    """Liefert der Server die Datei nicht, bleibt das alte Manifest und die alte Version."""
    datei, ziel, ablauf = _ausliefern(geheim, tmp_path, monkeypatch)
    alt = ziel / "aikido-kyu" / "0"
    alt.mkdir(parents=True)
    monkeypatch.setattr(bundle, "adressen_fehler", lambda *a: ["https://v.example/x: 404"])
    with pytest.raises(SystemExit, match="Manifest bleibt"):
        bundle.befehl_hochladen(HOCH)
    assert ablauf == [] and alt.exists()


def test_ohne_video_basis_geht_nichts_hinaus(geheim, tmp_path, monkeypatch):
    _gebaut(geheim, tmp_path)
    _echt(geheim)
    (geheim / "gitea-token").write_text("t")
    monkeypatch.setattr(bundle, "_laenge_fehler", lambda *a: [])
    monkeypatch.setattr(bundle, "videos_kopieren", lambda *a, **k: pytest.fail("nichts darf hinaus"))
    monkeypatch.setattr(bundle, "hochladen", lambda *a, **k: pytest.fail("nichts darf hinaus"))
    with pytest.raises(SystemExit, match="video-basis fehlt"):
        bundle.befehl_hochladen(type("A", (), {"nur_manifest": True, "verband_stimmt_zu": True, "probe": False}))


def test_build_ohne_schnittpunkte_wird_nicht_hochgeladen(geheim, tmp_path, monkeypatch):
    """Ein älterer Bau ohne Schnittpunkte: neu bauen."""
    _gebaut(geheim, tmp_path)
    _echt(geheim)
    m = bundle.manifest_lesen()
    del m["bundles"][0]["videos"][0]["kapitel"]
    bundle.manifest_schreiben(m)
    monkeypatch.setattr(bundle, "hochladen", lambda *a, **k: pytest.fail("nichts darf hinaus"))
    with pytest.raises(SystemExit, match="keine Schnittpunkte"):
        bundle.befehl_hochladen(type("A", (), {"nur_manifest": True, "verband_stimmt_zu": True, "probe": False}))


def test_adressen_prueft_groesse(monkeypatch):
    m = {"bundles": [{"id": "b", "version": 1, "videos": [{"datei": "a.mvb", "groesse": 5}, {"datei": "c.mvb", "groesse": 5}]}]}

    class Antwort:
        def __init__(self, laenge):
            self.headers = {"Content-Length": laenge}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(anfrage, timeout):
        assert anfrage.get_method() == "HEAD"
        if anfrage.full_url.endswith("c.mvb"):
            raise bundle.urllib.error.URLError("404")
        return Antwort("7")

    monkeypatch.setattr(bundle.urllib.request, "urlopen", urlopen)
    fehler = bundle.adressen_fehler(m, "https://v.example")
    assert len(fehler) == 2 and "7 Byte" in fehler[0] and "c.mvb" in fehler[1]


def test_hochladen_schickt_rohe_bytes(monkeypatch):
    """Ohne Content-Type setzt urllib application/x-www-form-urlencoded; Gitea liest den PUT dann als
    Formular und antwortet 500 ("request Content-Type isn't multipart/form-data")."""
    gesehen = []

    def urlopen(anfrage, timeout):
        gesehen.append(anfrage)
        if anfrage.get_method() == "DELETE":
            raise bundle.urllib.error.HTTPError(anfrage.full_url, 404, "fehlt", {}, None)
        return None

    monkeypatch.setattr(bundle.urllib.request, "urlopen", urlopen)
    bundle.hochladen("mitori-manifest", "1", "manifest.json", b"{}", "t")
    put = gesehen[-1]
    assert put.get_method() == "PUT"
    assert put.get_header("Content-type") == "application/octet-stream"


def test_schnittpunkte_aus_den_daten_ohne_pruefvermerk():
    k = bundle.schnittpunkte("aikido/k5")
    assert k and all(set(e) == {"id", "von", "bis"} for e in k)


def test_schnittpunkte_aus_eigener_datei(tmp_path):
    p = tmp_path / "schnitt.yaml"
    p.write_text("aikido/k5:\n  kapitel:\n  - {id: a, von: 1.5, bis: 3, pruefen: true}\n", encoding="utf-8")
    assert bundle.schnittpunkte("aikido/k5", p) == [{"id": "a", "von": 1.5, "bis": 3}]
    assert bundle.schnittpunkte("aikido/k4", p) == []


def test_schnittpunkte_ohne_technik_die_im_video_fehlt(tmp_path):
    """`fehlt: true`: Die Technik ist nicht im Video, sie hat keine Stelle (wie tools/daten.py)."""
    p = tmp_path / "schnitt.yaml"
    p.write_text("aikido/k1:\n  kapitel:\n  - {id: a, von: 1, bis: 2}\n  - {id: b, fehlt: true}\n", encoding="utf-8")
    assert bundle.schnittpunkte("aikido/k1", p) == [{"id": "a", "von": 1, "bis": 2}]


def test_jedes_video_hat_gueltige_schnittpunkte():
    """Die echten Daten: Sonst hielte erst der Bau an, nach Stunden des Kodierens."""
    for b in bundle.definitionen().values():
        for v in b["videos"]:
            assert bundle.schnitt_fehler(v, bundle.schnittpunkte(v), None) == []


def test_schnitt_fehler():
    gut = [{"id": "a", "von": 1, "bis": 9.5}]
    assert bundle.schnitt_fehler("v", gut, 9.0) == []
    assert bundle.schnitt_fehler("v", gut, None) == []
    assert "keine Schnittpunkte" in bundle.schnitt_fehler("v", [], 9.0)[0]
    assert "endet bei" in bundle.schnitt_fehler("v", [{"id": "a", "von": 1, "bis": 20}], 9.0)[0]
    assert "von 5 bis 2" in bundle.schnitt_fehler("v", [{"id": "a", "von": 5, "bis": 2}], None)[0]


def test_fertig_verschluesselt_und_gilt_nicht_als_testbau(geheim, tmp_path, monkeypatch):
    """Von Hand gemastert: nichts wird kodiert, die Datei bleibt, und sie darf hinaus."""
    ordner = tmp_path / "remaster"
    daten = {v: {"datei": f"{v}.mkv", "beschnitt": {}} for v in bundle.definitionen()["aikido-kyu"]["videos"]}
    for info in daten.values():
        (ordner / info["datei"]).parent.mkdir(parents=True, exist_ok=True)
        (ordner / info["datei"]).write_bytes(b"gemastert" * 100)
    schnitt = tmp_path / "schnitt.yaml"
    schnitt.write_text(yaml.safe_dump({v: {"kapitel": bundle.schnittpunkte(v)} for v in daten}), encoding="utf-8")
    monkeypatch.setattr(bundle, "videodaten", lambda: daten)
    monkeypatch.setattr(bundle, "bilder", lambda p: 100)
    monkeypatch.setattr(bundle, "laufzeit", lambda p: 1e6)
    monkeypatch.setattr(bundle.shutil, "which", lambda name: "/usr/bin/" + name)    # auch ohne ffprobe in der CI
    monkeypatch.setattr(bundle, "beschnitten", lambda *a: pytest.fail("nichts wird kodiert"))
    args = type("A", (), {"bundle": "aikido-kyu", "videos": str(ordner), "version": None, "hinweis": "",
                          "ohne_kodieren": False, "fertig": True, "schnitt": str(schnitt)})
    bundle.befehl_build(args)
    eintrag = bundle.manifest_lesen()["bundles"][0]
    assert not bundle.ist_testbau(eintrag)
    assert eintrag["videos"][0]["kapitel"] == bundle.schnittpunkte("aikido/k5")
    monkeypatch.setattr(bundle, "laufzeit", lambda p: 5.0)
    args.version = None
    with pytest.raises(SystemExit, match="endet bei"):
        bundle.befehl_build(args)


def test_altes_manifest_wird_format_2(geheim):
    geheim.mkdir()
    (geheim / "manifest.json").write_text(json.dumps({"format": 1, "basis": "x", "bundles": [], "codes": {}}))
    m = bundle.manifest_lesen()
    assert m["format"] == 2 and "basis" not in m


# ── Funde des Reviews ──

def test_schnitt_mit_falscher_oder_fehlender_technik_stoppt(tmp_path):
    """Sonst nähme die App für diese Technik die Stelle der alten Zeitlinie."""
    echt = bundle.schnittpunkte("aikido/k5")
    assert bundle.schnitt_ids_fehler("aikido/k5", echt) == []
    assert "fehlt" in bundle.schnitt_ids_fehler("aikido/k5", echt[1:])[0]
    falsch = echt + [{"id": "aikido/tippfehler", "von": 1, "bis": 2}]
    assert "unbekannt" in bundle.schnitt_ids_fehler("aikido/k5", falsch)[0]


def _mit_manifest_stub(geheim, tmp_path, monkeypatch, hochladen):
    _, ziel, _ = _ausliefern(geheim, tmp_path, monkeypatch)
    monkeypatch.setattr(bundle, "hochladen", hochladen)
    monkeypatch.setattr(bundle.time, "sleep", lambda s: None)
    return ziel


@rsync
def test_manifest_wird_wiederholt(geheim, tmp_path, monkeypatch):
    versuche = []

    def hochladen(*a, **k):
        versuche.append(1)
        if len(versuche) < 3:
            raise bundle.urllib.error.URLError("weg")

    ziel = _mit_manifest_stub(geheim, tmp_path, monkeypatch, hochladen)
    alt = ziel / "aikido-kyu" / "0"
    alt.mkdir(parents=True)
    bundle.befehl_hochladen(HOCH)
    assert len(versuche) == 3 and not alt.exists()


@rsync
def test_manifest_scheitert_nennt_den_befehl_und_laesst_die_alte_version(geheim, tmp_path, monkeypatch):
    """Nach dem DELETE kann es auf Gitea fehlen: Das muss gesagt werden, die alten Dateien bleiben."""

    def hochladen(*a, **k):
        raise bundle.urllib.error.URLError("weg")

    ziel = _mit_manifest_stub(geheim, tmp_path, monkeypatch, hochladen)
    alt = ziel / "aikido-kyu" / "0"
    alt.mkdir(parents=True)
    with pytest.raises(SystemExit, match="--nur-manifest"):
        bundle.befehl_hochladen(HOCH)
    assert alt.exists()


def test_fertig_verlangt_einen_eigenen_ordner(geheim):
    """Ohne --videos wären es die Originale, die dann als beschnitten gälten."""
    args = type("A", (), {"bundle": "aikido-kyu", "videos": bundle.ORIGINALE, "version": None, "hinweis": "",
                          "ohne_kodieren": False, "fertig": True, "schnitt": None})
    with pytest.raises(SystemExit, match="--videos"):
        bundle.befehl_build(args)


def test_fertig_und_ohne_kodieren_schliessen_sich_aus(monkeypatch):
    monkeypatch.setattr(bundle.sys, "argv", ["bundle", "build", "aikido-kyu", "--fertig", "--ohne-kodieren"])
    with pytest.raises(SystemExit):
        bundle.main()


def test_scheitert_das_aufraeumen_sagt_es_das(geheim, monkeypatch):
    monkeypatch.setattr(bundle.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 1}))
    b = {"id": "x", "version": 1, "videos": []}
    with pytest.raises(SystemExit, match="Manifest bleibt"):
        bundle.videos_kopieren(b, "z")
    with pytest.raises(SystemExit, match="alte Versionen") as e:
        bundle.videos_kopieren(b, "z", aufraeumen=True)
    assert "Manifest bleibt" not in str(e.value)


def test_keine_alte_oder_gleiche_version(geheim, tmp_path):
    """Die gleiche Nummer ersetzte auf dem Server die Datei, die gerade gilt."""
    _gebaut(geheim, tmp_path)
    args = type("A", (), {"bundle": "aikido-kyu", "videos": "x", "version": 1, "hinweis": "",
                          "ohne_kodieren": True, "schnitt": None})
    with pytest.raises(SystemExit, match="Version 1"):
        bundle.befehl_build(args)


def test_alle_baut_bauten_ohne_schnittpunkte_neu(geheim, tmp_path, monkeypatch):
    _gebaut(geheim, tmp_path)
    _echt(geheim)
    gebaut = []
    monkeypatch.setattr(bundle, "befehl_build", lambda args: gebaut.append(args.bundle))
    bundle.befehl_alle(type("A", (), {"neu": False, "ohne_kodieren": False}))
    assert "aikido-kyu" not in gebaut
    m = bundle.manifest_lesen()
    del m["bundles"][0]["videos"][0]["kapitel"]
    bundle.manifest_schreiben(m)
    bundle.befehl_alle(type("A", (), {"neu": False, "ohne_kodieren": False}))
    assert "aikido-kyu" in gebaut


def _fertig_args(ordner, schnitt):
    return type("A", (), {"bundle": "aikido-kyu", "videos": str(ordner), "version": None, "hinweis": "",
                          "ohne_kodieren": False, "fertig": True, "schnitt": str(schnitt)})


def test_build_stoppt_bei_falscher_technik(geheim, tmp_path, monkeypatch):
    ordner = tmp_path / "remaster"
    ordner.mkdir()
    (ordner / "v.mkv").write_bytes(b"gemastert")
    monkeypatch.setattr(bundle, "videodaten", lambda: {v: {"datei": "v.mkv", "beschnitt": {}} for v in bundle.definitionen()["aikido-kyu"]["videos"]})
    monkeypatch.setattr(bundle, "bilder", lambda p: 100)
    monkeypatch.setattr(bundle.shutil, "which", lambda name: None)
    schnitt = tmp_path / "schnitt.yaml"
    schnitt.write_text("aikido/k5:\n  kapitel:\n  - {id: aikido/tippfehler, von: 1, bis: 2}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="unbekannte Technik"):
        bundle.befehl_build(_fertig_args(ordner, schnitt))
    assert not list((geheim / "aus").rglob("*.mvb"))


def test_doppelte_technik_stoppt():
    echt = bundle.schnittpunkte("aikido/k5")
    fehler = bundle.schnitt_ids_fehler("aikido/k5", echt + [{**echt[0], "von": 1, "bis": 2}])
    assert "doppelt" in fehler[0]


@pytest.mark.parametrize("schreibweise", ["{o}/", "{o}/../{n}"])
def test_fertig_erkennt_die_originale_in_jeder_schreibweise(geheim, tmp_path, monkeypatch, schreibweise):
    o = tmp_path / "Mitori Videos"
    o.mkdir()
    monkeypatch.setattr(bundle, "ORIGINALE", str(o))
    args = _fertig_args(schreibweise.format(o=o, n=o.name), "x")
    with pytest.raises(SystemExit, match="--videos"):
        bundle.befehl_build(args)


def _daten_nach_dem_bau_geaendert(geheim, tmp_path, monkeypatch):
    _gebaut(geheim, tmp_path)
    _echt(geheim)
    m = bundle.manifest_lesen()
    m["bundles"][0]["videos"][0]["kapitel"].pop()
    bundle.manifest_schreiben(m)
    monkeypatch.setattr(bundle, "_laenge_fehler", lambda *a: [])
    monkeypatch.setattr(bundle.shutil, "which", lambda name: "/usr/bin/" + name)


def test_hochladen_prueft_die_techniken_gegen_die_daten(geheim, tmp_path, monkeypatch):
    """Ändern sich die Daten nach dem Bau, gehen die Videos nicht hinaus."""
    _daten_nach_dem_bau_geaendert(geheim, tmp_path, monkeypatch)
    monkeypatch.setattr(bundle, "videos_kopieren", lambda *a, **k: pytest.fail("nichts darf hinaus"))
    monkeypatch.setattr(bundle, "hochladen", lambda *a, **k: pytest.fail("nichts darf hinaus"))
    with pytest.raises(SystemExit, match="Schnittpunkt fehlt"):
        bundle.befehl_hochladen(HOCH)


def test_sperre_haengt_nicht_an_den_daten(geheim, tmp_path, monkeypatch):
    """Eine Sperre muss sofort wirken: Die Schnittpunkte gehören zur Datei, nicht zum Datenstand."""
    _daten_nach_dem_bau_geaendert(geheim, tmp_path, monkeypatch)
    (geheim / "gitea-token").write_text("t")
    (geheim / "video-basis").write_text("https://v.example/m")
    monkeypatch.setattr(bundle, "adressen_fehler", lambda *a: [])
    gesendet = []
    monkeypatch.setattr(bundle, "hochladen", lambda *a, **k: gesendet.append(a))
    bundle.befehl_hochladen(type("A", (), {"nur_manifest": True, "verband_stimmt_zu": True, "probe": False}))
    assert len(gesendet) == 1


# ── Lernpakete ──

PAKET = {
    "titel": "Shirakawa", "titel_en": "Shirakawa EN", "sparte": "aikido",
    "videos": [{"id": "shirakawa-1/v1", "datei": "S/V1.mp4", "titel": "Vol. 1"}],
    "abschnitte": [{"titel": "Grund", "techniken": [
        {"id": "irimi", "name": "Irimi-nage", "angriff": "Shomen-uchi", "video": "shirakawa-1/v1", "von": 1, "bis": 9.5}]}],
}


def _paket_args(ordner, **mehr):
    args = {"bundle": "shirakawa-1", "videos": str(ordner), "version": None, "hinweis": "",
            "ohne_kodieren": True, "fertig": False, "schnitt": None}
    return type("A", (), args | mehr)


@pytest.fixture
def lernpaket(geheim, tmp_path, monkeypatch):
    """Ein Lernpaket in einem Test-Ordner, ein Dummy-Video; ffmpeg und ffprobe sind ersetzt."""
    pakete = tmp_path / "pakete"
    pakete.mkdir()
    (pakete / "shirakawa-1.yaml").write_text(yaml.safe_dump(PAKET, allow_unicode=True, sort_keys=False), encoding="utf-8")
    videos = tmp_path / "lernvideos"
    (videos / "S").mkdir(parents=True)
    (videos / "S" / "V1.mp4").write_bytes(b"video" * 1000)
    monkeypatch.setattr(paket, "PAKETE", pakete)
    monkeypatch.setattr(paket, "programmdaten", lambda: (set(), {"aikido/k5"}))
    monkeypatch.setattr(bundle, "bilder", lambda p: 100)
    monkeypatch.setattr(bundle, "laufzeit", lambda p: 10.0)
    monkeypatch.setattr(bundle, "_laenge_fehler", lambda *a: [])
    monkeypatch.setattr(bundle.shutil, "which", lambda name: "/usr/bin/" + name)
    return pakete, videos


def _gebaut_paket(lernpaket, **mehr):
    bundle.befehl_build(_paket_args(lernpaket[1], **mehr))
    return bundle.manifest_lesen()["lernpakete"][0]


def test_paket_fertig_verlangt_einen_eigenen_ordner(geheim, lernpaket):
    """Ohne --videos wären es die Lernvideos im Original, die dann als kodiert gälten."""
    with pytest.raises(SystemExit, match="--videos"):
        bundle.befehl_build(_paket_args(lernpaket[1], videos=None, ohne_kodieren=False, fertig=True))


def test_paket_bauen(geheim, lernpaket):
    e = _gebaut_paket(lernpaket)
    m = bundle.manifest_lesen()
    assert m["format"] == 2 and m["bundles"] == []
    assert set(e) == {"id", "version", "titel", "titel_en", "videos", "inhalt", "hinweis"}
    assert (e["id"], e["version"], e["titel_en"], e["hinweis"]) == ("shirakawa-1", 1, "Shirakawa EN", "")
    v = e["videos"][0]
    assert v["video"] == "shirakawa-1/v1" and v["datei"] == "shirakawa-1-v1.mvb" and "kapitel" not in v
    assert v["bilder"] == 100 and v["beschnitten"] is False and v["klar"] == 5000
    aus = geheim / "aus" / "shirakawa-1" / "1"
    assert (aus / v["datei"]).stat().st_size == v["groesse"]
    i = e["inhalt"]
    assert i["datei"] == "inhalt.mvb" and i["format"] == 1
    assert (aus / "inhalt.mvb").stat().st_size == i["groesse"]
    bundle.entschluesselt(aus / "inhalt.mvb", geheim / "klar.json", bundle.schluessel("shirakawa-1"))
    j = json.loads((geheim / "klar.json").read_text(encoding="utf-8"))
    assert j == paket.inhalt("shirakawa-1") and i["klar"] == (geheim / "klar.json").stat().st_size
    assert j["abschnitte"][0]["techniken"][0]["id"] == "lern/shirakawa-1/irimi"
    assert j["abschnitte"][0]["techniken"][0]["angriff"]["jp"] == "正面打ち"
    assert not (geheim / "arbeit" / "shirakawa-1" / "inhalt.json").exists()


def test_paket_hat_hoehere_version(geheim, lernpaket):
    _gebaut_paket(lernpaket)
    with pytest.raises(SystemExit, match="Version 1"):
        bundle.befehl_build(_paket_args(lernpaket[1], version=1))
    assert _gebaut_paket(lernpaket)["version"] == 2


def test_paket_kodiert_ohne_schnitt(geheim, lernpaket, monkeypatch):
    """Ohne `beschnitt` nur HEVC: beschnitten() bekommt einen leeren Beschnitt (Filter null)."""
    gesehen = []

    def kodiere(quelle, ziel, beschnitt):
        gesehen.append(beschnitt)
        ziel.write_bytes(b"hevc")

    monkeypatch.setattr(bundle, "beschnitten", kodiere)
    e = _gebaut_paket(lernpaket, ohne_kodieren=False)
    assert gesehen == [{}] and e["videos"][0]["beschnitten"] is True and e["videos"][0]["klar"] == 4


def test_paket_fertig(geheim, lernpaket, monkeypatch):
    monkeypatch.setattr(bundle, "beschnitten", lambda *a: pytest.fail("nichts wird kodiert"))
    e = _gebaut_paket(lernpaket, ohne_kodieren=False, fertig=True)
    assert not bundle.ist_testbau(e)


def test_paket_standardordner_der_videos():
    assert bundle.LERNVIDEOS == str(bundle.WURZEL.parent / "Mitori Lernvideos")


def test_paket_entwurf_wird_nicht_gebaut(geheim, lernpaket):
    d = json.loads(json.dumps(PAKET))
    d["abschnitte"][0]["techniken"][0]["pruefen"] = True
    (lernpaket[0] / "shirakawa-1.yaml").write_text(yaml.safe_dump(d), encoding="utf-8")
    with pytest.raises(SystemExit, match="Entwurf"):
        bundle.befehl_build(_paket_args(lernpaket[1]))
    assert bundle.manifest_lesen()["lernpakete"] == [] and not (geheim / "aus").exists()


def test_paket_mit_fehler_wird_nicht_gebaut(geheim, lernpaket):
    d = json.loads(json.dumps(PAKET))
    d["sparte"] = "judo"
    (lernpaket[0] / "shirakawa-1.yaml").write_text(yaml.safe_dump(d), encoding="utf-8")
    with pytest.raises(SystemExit, match="Sparte"):
        bundle.befehl_build(_paket_args(lernpaket[1]))


def test_paket_technik_hinter_dem_videoende(geheim, lernpaket, monkeypatch):
    monkeypatch.setattr(bundle, "laufzeit", lambda p: 5.0)
    with pytest.raises(SystemExit, match="endet bei"):
        bundle.befehl_build(_paket_args(lernpaket[1]))
    assert bundle.manifest_lesen()["lernpakete"] == []


def test_paket_verifizieren(geheim, lernpaket):
    _gebaut_paket(lernpaket)
    assert bundle.verifiziert("shirakawa-1") == []
    k = bundle.schluessel("shirakawa-1")
    inhalt = geheim / "aus" / "shirakawa-1" / "1" / "inhalt.mvb"
    echt = inhalt.read_bytes()

    roh = bytearray(echt)
    roh[-5] ^= 1
    inhalt.write_bytes(roh)
    assert any("inhalt.mvb" in f for f in bundle.verifiziert("shirakawa-1"))

    fremd = geheim / "fremd.json"                               # heil, aber das falsche Paket
    fremd.write_text('{"id": "anderes"}', encoding="utf-8")
    g, sha, klar = bundle.verschluesselt(fremd, inhalt, k)
    m = bundle.manifest_lesen()
    m["lernpakete"][0]["inhalt"].update(groesse=g, sha256=sha, klar=klar)
    bundle.manifest_schreiben(m)
    assert any("gehört nicht zu shirakawa-1" in f for f in bundle.verifiziert("shirakawa-1"))

    fremd.write_text("kein json", encoding="utf-8")
    g, sha, klar = bundle.verschluesselt(fremd, inhalt, k)
    m["lernpakete"][0]["inhalt"].update(groesse=g, sha256=sha, klar=klar)
    bundle.manifest_schreiben(m)
    assert any("kein JSON" in f for f in bundle.verifiziert("shirakawa-1"))

    inhalt.unlink()
    assert any("inhalt.mvb: fehlt" in f for f in bundle.verifiziert("shirakawa-1"))


def test_paket_stand_und_codes(geheim, lernpaket, capsys):
    assert any(z == "shirakawa-1: nicht gebaut" for z in bundle.stand_zeilen())
    _gebaut_paket(lernpaket)
    bundle.befehl_codes(type("A", (), {"bundle": "shirakawa-1", "anzahl": 2, "fuer": "Dojo"}))
    zeile = next(z for z in bundle.stand_zeilen() if z.startswith("shirakawa-1"))
    assert "Version 1" in zeile and "2 Codes" in zeile and "Testbau" in zeile
    code = (geheim / "codes" / "shirakawa-1.csv").read_text(encoding="utf-8").splitlines()[1].split(",")[0]
    bundle.befehl_pruefen(type("A", (), {"code": code}))
    assert "öffnet shirakawa-1: ja" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="unbekanntes Bundle"):
        bundle.befehl_codes(type("A", (), {"bundle": "gibt-es-nicht", "anzahl": 1, "fuer": ""}))


def test_paket_verifizieren_ohne_name_nimmt_alle(geheim, lernpaket, capsys):
    _gebaut_paket(lernpaket)
    bundle.befehl_verifizieren(type("A", (), {"bundle": None}))
    assert "1 Bundles in Ordnung" in capsys.readouterr().err


def test_alle_baut_pakete_und_ueberspringt_entwuerfe(geheim, lernpaket, monkeypatch, capsys):
    d = json.loads(json.dumps(PAKET))
    d["videos"][0]["id"] = "entwurf/v1"
    d["abschnitte"][0]["techniken"][0].update(video="entwurf/v1", pruefen=True)
    (lernpaket[0] / "entwurf.yaml").write_text(yaml.safe_dump(d), encoding="utf-8")
    gebaut = []
    monkeypatch.setattr(bundle, "befehl_build", lambda args: gebaut.append(args.bundle))
    bundle.befehl_alle(type("A", (), {"neu": False, "ohne_kodieren": True}))
    assert "shirakawa-1" in gebaut and "entwurf" not in gebaut
    assert "entwurf ist ein Entwurf" in capsys.readouterr().err


def test_alle_nimmt_je_art_ihren_ordner(geheim, lernpaket, monkeypatch):
    ordner = {}
    monkeypatch.setattr(bundle, "befehl_build", lambda args: ordner.setdefault(args.bundle, args.videos))
    bundle.befehl_alle(type("A", (), {"neu": False, "ohne_kodieren": True, "videos": "pruefung", "lernvideos": "lern"}))
    assert ordner["shirakawa-1"] == "lern"
    assert ordner["aikido-kyu"] == "pruefung"


def test_alle_baut_gebautes_paket_nicht_neu(geheim, lernpaket, monkeypatch):
    _gebaut_paket(lernpaket, ohne_kodieren=False, fertig=True)
    gebaut = []
    monkeypatch.setattr(bundle, "befehl_build", lambda args: gebaut.append(args.bundle))
    bundle.befehl_alle(type("A", (), {"neu": False, "ohne_kodieren": False}))
    assert "shirakawa-1" not in gebaut


def test_veroeffentlichtes_manifest_hat_adressen_fuer_den_inhalt(geheim, lernpaket):
    _gebaut_paket(lernpaket)
    m = bundle.manifest_lesen()
    aus = bundle.veroeffentlichtes_manifest(m, "https://v.example/m")
    e = aus["lernpakete"][0]
    assert e["inhalt"]["url"] == "https://v.example/m/shirakawa-1/1/inhalt.mvb"
    assert e["videos"][0]["url"] == "https://v.example/m/shirakawa-1/1/shirakawa-1-v1.mvb"
    assert "url" not in m["lernpakete"][0]["inhalt"] and "url" not in m["lernpakete"][0]["videos"][0]


def test_adressen_pruefen_auch_den_inhalt(monkeypatch):
    m = {"bundles": [], "lernpakete": [{"id": "p", "version": 1, "videos": [{"datei": "a.mvb", "groesse": 5}],
                                         "inhalt": {"datei": "inhalt.mvb", "groesse": 5}}]}
    abgefragt = []

    class Antwort:
        headers = {"Content-Length": "5"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(bundle.urllib.request, "urlopen", lambda anfrage, timeout: abgefragt.append(anfrage.full_url) or Antwort())
    assert bundle.adressen_fehler(m, "https://v.example") == []
    assert abgefragt == ["https://v.example/p/1/a.mvb", "https://v.example/p/1/inhalt.mvb"]


def test_altes_manifest_bekommt_lernpakete(geheim):
    geheim.mkdir()
    (geheim / "manifest.json").write_text(json.dumps({"format": 2, "bundles": [], "codes": {}}))
    assert bundle.manifest_lesen()["lernpakete"] == []


@rsync
def test_paket_hochladen(geheim, lernpaket, tmp_path, monkeypatch):
    """Videos und Inhalt gehen zum Server, das Manifest nennt beide mit Adresse; ohne Kapitel gibt es keinen Fehler."""
    _gebaut_paket(lernpaket, ohne_kodieren=False, fertig=True)
    ziel = tmp_path / "server"
    ziel.mkdir()
    (geheim / "gitea-token").write_text("t")
    (geheim / "video-basis").write_text("https://v.example/m/\n")
    (geheim / "video-ziel").write_text(str(ziel))
    gesendet = []
    monkeypatch.setattr(bundle.shutil, "which", shutil.which)
    monkeypatch.setattr(bundle, "bilder", lambda p: 100)
    monkeypatch.setattr(bundle, "adressen_fehler", lambda m, basis: [])
    monkeypatch.setattr(bundle, "hochladen", lambda paket_, version, name, daten, token, laenge=None: gesendet.append(json.loads(daten)))
    bundle.befehl_hochladen(HOCH)
    assert sorted(p.name for p in (ziel / "shirakawa-1" / "1").iterdir()) == ["inhalt.mvb", "shirakawa-1-v1.mvb"]
    assert gesendet[0]["lernpakete"][0]["inhalt"]["url"] == "https://v.example/m/shirakawa-1/1/inhalt.mvb"


def test_paket_testbau_wird_nicht_hochgeladen(geheim, lernpaket, monkeypatch):
    _gebaut_paket(lernpaket)
    with pytest.raises(SystemExit, match="Testbau"):
        bundle.befehl_hochladen(type("A", (), {"nur_manifest": False, "verband_stimmt_zu": True, "probe": False}))
