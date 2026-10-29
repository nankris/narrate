"""Round 6 regressions: silence, establishing place, complete cues, and title-only claims. Offline only."""
from narrate.director import DEFAULTS, has_finite_verb
from narrate.config import load_config
from tests.test_director import postcheck_director


def test_max_silence_routes_most_informative_skipped_gap_to_batched_repair(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch, max_silent_run_s=20)
    for g in d.scriptable():
        d.skip_gap(g['id'], 'routine')
    rescued = d.enforce_max_silence()
    assert rescued == [2]  # equal event counts: the longest gap wins
    assert 2 not in d.skipped and 2 not in d.dropped and 2 in d.failed
    reason = d.failed[2]['reasons'][0]
    assert 'concrete, not-yet-mentioned visible detail' in reason and 'never repeat earlier cues' in reason
    assert DEFAULTS['max_silent_run_s'] == load_config()['director']['max_silent_run_s'] == 20


def test_short_silent_run_is_left_alone(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch, max_silent_run_s=30)
    for g in d.scriptable():
        d.skip_gap(g['id'], 'routine')
    assert d.enforce_max_silence() == []


def test_english_complete_sentence_lint_and_low_false_positives(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    d.pending[0] = {'text': 'In the kitchen, the cook pours water into flour.', 'evidence': ['e1']}
    assert any('final punctuation' in p for p in d.check_cue(1, 'She kneads the dough into a ball', ['e3'])[1])
    assert any('no finite verb' in p for p in d.check_cue(1, 'A ball on the mat.', ['e3'])[1])
    assert not has_finite_verb('A ball on the mats.')
    assert d.check_cue(1, 'She kneads the dough into a ball.', ['e3'])[1] == []


def test_hindi_danda_normaliser_changes_punctuation_only(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    assert d.normalise_hindi('हाथ आटा गूँधते हैं') == 'हाथ आटा गूँधते हैं।'
    assert d.normalise_hindi('हाथ आटा गूँधते हैं।') == 'हाथ आटा गूँधते हैं।'


def test_title_only_claims_repaired_but_setting_and_object_nouns_allowed(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    d.bible = {**d.bible, 'objects': [*d.bible['objects'], 'roti']}
    d.context = 'Historic first roti harvest in a home kitchen'
    leaked = d.context_only_claims('In the home kitchen, the cook photographs the historic first harvest.')
    assert leaked == ['first', 'harvest', 'historic']
    assert d.context_only_claims('In the home kitchen, the cook rolls the roti.') == []
    problems = d.check_cue(0, 'In the home kitchen, the cook photographs the historic first harvest.', ['e1'])[1]
    assert any('remove claims taken only from the title' in p for p in problems)


def test_establishing_hint_is_idiomatic_and_setting_word_passes(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    d.bible = {**d.bible, 'setting': 'a space station', 'place': 'space station',
               'cast': [{**d.bible['cast'][0], 'descriptor': 'the astronaut'}]}
    problems = d.check_cue(0, 'The astronaut reaches into the growth chamber.', ['e1'])[1]
    assert any('name the bible place' in p for p in problems)
    assert d.check_cue(0, 'Aboard the space station, the astronaut reaches into the chamber.', ['e1'])[1] == []
