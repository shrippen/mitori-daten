"""tools/kapitel.py: ein neuer Lauf behält, was von Hand am Video steht."""
import importlib.util
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kapitel", WURZEL / "tools" / "kapitel.py")
kapitel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kapitel)

STANDARD = kapitel.BESCHNITT["aikido"]
VON_HAND = {"hoehe": 478, "y": 70, "h": 360, "verhaeltnis": round(768 / 360, 4)}


def lauf(schluessel):
    """Was ein Lauf für ein Video schreibt: Beschnitt aus den Konstanten, neue Kapitel."""
    return {"datei": "Aikido/5. Kyu.mkv", "beschnitt": STANDARD, "kapitel": [{"id": schluessel, "von": 1, "bis": 2}]}


def test_beschnitt_von_hand_bleibt():
    # mitori-tools (Beschnitt) korrigiert den Streifen und setzt pruefen_beschnitt.
    alt = {"aikido/k5": {"datei": "Aikido/5. Kyu.mkv", "pruefen_beschnitt": True, "beschnitt": VON_HAND,
                         "kapitel": [{"id": "alt", "von": 0, "bis": 1}]}}
    neu = kapitel.zusammenfuehren(alt, {"aikido/k5": lauf("neu")})
    v = neu["aikido/k5"]
    assert v["beschnitt"] == VON_HAND
    assert v["pruefen_beschnitt"] is True
    assert v["kapitel"] == [{"id": "neu", "von": 1, "bis": 2}]
    assert list(v) == ["datei", "pruefen_beschnitt", "beschnitt", "kapitel"]


def test_geteilter_beschnitt_bleibt_geteilt():
    # Zwei Videos auf einem Anker (&id001 / *id001): nach dem Lauf weiter dasselbe Objekt.
    block = dict(VON_HAND)
    alt = {"aikido/k5": {"datei": "a", "beschnitt": block, "kapitel": []},
           "aikido/k4": {"datei": "b", "beschnitt": block, "kapitel": []}}
    neu = kapitel.zusammenfuehren(alt, {"aikido/k5": lauf("x")})
    assert neu["aikido/k5"]["beschnitt"] is neu["aikido/k4"]["beschnitt"]


def test_neues_video_bekommt_standard():
    neu = kapitel.zusammenfuehren({}, {"aikido/k5": lauf("x")})
    assert neu["aikido/k5"]["beschnitt"] == STANDARD
    assert list(neu["aikido/k5"]) == ["datei", "beschnitt", "kapitel"]
