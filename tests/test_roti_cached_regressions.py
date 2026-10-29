import json
import re
from pathlib import Path


PLAN = Path('runs/ext/final/roti/pause_plan.json')


def texts():
    return [p['cue_text'] for p in json.loads(PLAN.read_text())['pauses']]


def test_roti_rolling_is_not_called_twisting():
    assert not any(re.search(r'\btwist(?:s|ed|ing)?\b', text, re.I) for text in texts())


def test_roti_plate_is_not_called_a_bowl():
    cover = next(text for text in texts() if re.search(r'\bcover(?:s|ed|ing)?\b', text, re.I))
    assert 'plate' in cover.lower()
    assert not re.search(r'\bwhite bowl\b|\binverted bowl\b', cover, re.I)


def test_roti_has_no_duplicate_oil_pour_cue():
    oil_pours = [text for text in texts() if re.search(
        r'\b(?:pour(?:s|ed|ing)?|spoon(?:s|ed|ing)?)\b.{0,45}\boil\b|\boil\b.{0,45}\b(?:pour(?:s|ed|ing)?|spoon(?:s|ed|ing)?)\b', text, re.I)]
    assert len(oil_pours) <= 1
