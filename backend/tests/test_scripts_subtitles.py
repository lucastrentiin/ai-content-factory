import pytest

from app.media.subtitles import build_ass, chunk_segment
from app.services.scripts import normalize_script


def test_normalize_script_fills_defaults_and_adds_speakers():
    raw = {"title": "T", "locations": [{"name": "Casa", "setting_type": "invalido"}],
           "scenes": [{"narration": "Era uma vez.", "dialogue": [{"character": "Ana", "text": "Oi!", "emotion": "xyz"}],
                       "camera": "voar", "location": "Lugar inexistente"}]}
    s = normalize_script(raw)
    sc = s["scenes"][0]
    assert s["locations"][0]["setting_type"] == "room"
    assert sc["camera"] == "static" and sc["location"] == "Casa"
    assert sc["dialogue"][0]["emotion"] == "neutral"
    assert any(c["name"] == "Ana" for c in s["characters"])
    assert any(c["name"] == "Ana" for c in sc["characters"])  # quem fala aparece em cena
    assert sc["duration_s"] >= 2


def test_normalize_rejects_empty():
    with pytest.raises(ValueError):
        normalize_script({"scenes": []})
    with pytest.raises(ValueError):
        normalize_script({"scenes": [{"narration": "", "dialogue": []}]})


def test_captions_use_word_timings_and_ass_output(tmp_path):
    caps = chunk_segment("um dois três quatro", 1.0, 3.0, 3,
                         [{"start": 0, "end": .4}, {"start": .5, "end": .9}, {"start": 1, "end": 1.3}, {"start": 1.4, "end": 1.9}])
    assert len(caps) == 2 and caps[0].start == 1.0 and abs(caps[1].end - 2.9) < 1e-9
    prop = chunk_segment("a bb ccc", 0, 3, 3)
    assert prop[0].start == 0 and abs(prop[0].end - 3) < 1e-9
    p = build_ass(caps, tmp_path / "s.ass", width=1080, height=1920, watermark={"text": "@canal"})
    txt = p.read_text()
    assert "Dialogue:" in txt and "\\k" in txt and "@canal" in txt
