import json
from pathlib import Path
from narrate.extended_director import duplicate_evidence, unsupported_terms

def test_vocabulary_grounding_uses_runtime_perception_across_domains():
    transport = [{'what': 'A mechanic tightens a bicycle chain', 'change': 'the chain becomes taut'}]
    science = [{'what': 'A researcher labels a glass vial', 'change': 'a label appears'}]
    assert unsupported_terms('The mechanic tightens the bicycle chain.', transport, {'cast':[{'descriptor':'the mechanic'}], 'objects':['bicycle chain']}, {}) == []
    assert unsupported_terms('The researcher labels the glass vial.', science, {'cast':[{'descriptor':'the researcher'}], 'objects':['glass vial']}, {}) == []
    assert 'helmet' in unsupported_terms('The mechanic lifts a helmet.', transport, {'cast':[{'descriptor':'the mechanic'}], 'objects':['bicycle chain']}, {})
    assert 'microscope' in unsupported_terms('A microscope appears.', science, {'cast':[], 'objects':[]}, {})

def test_duplicate_event_detection_uses_ids_and_overlapping_evidence():
    timeline = [{'id':'e1','t_start':1,'t_end':3,'what':'A cyclist removes the rear wheel'}, {'id':'e2','t_start':2,'t_end':4,'what':'The cyclist removes a rear wheel'}, {'id':'e3','t_start':8,'t_end':9,'what':'A cell divides under a microscope'}]
    accepted = {1:{'evidence':['e1'],'text':'first'}, 2:{'evidence':['e3'],'text':'second'}}
    assert duplicate_evidence({'evidence':['e1']}, accepted, timeline) == [1]
    assert duplicate_evidence({'evidence':['e2']}, accepted, timeline) == [1]
    assert duplicate_evidence({'evidence':['e3']}, accepted, timeline) == [2]

def test_reviewed_fixture_has_no_recorded_contradiction():
    report = json.loads(Path('runs/ext/final/roti/report.json').read_text())
    for history in report.get('cue_history', {}).values():
        final = [row for row in history if row.get('step') in {'verify','rescue_verify','rescue_strike_verify'}]
        if final: assert final[-1].get('verdict') != 'contradicted'
