import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from app.app import SpendLedger, validate_upload, trace_html, discover_cached, ist_date


def test_caps_and_rollover(tmp_path):
    ledger = SpendLedger(tmp_path/'spend.json', .3)
    before = datetime(2026,10,27,18,29,tzinfo=timezone.utc)
    after = datetime(2026,10,27,18,31,tzinfo=timezone.utc)
    day, amount = ledger.reserve(.1,.25,.5,60,before)
    assert amount == pytest.approx(.15)
    ledger.settle(day,amount,.12)
    with pytest.raises(ValueError):
        ledger.reserve(.24,.25,.5,60,before)
    d, a = ledger.reserve(0,1,1,60,before)
    assert a == pytest.approx(.18)
    with pytest.raises(ValueError):
        ledger.reserve(0,1,1,60,before)
    d2, a2 = ledger.reserve(0,1,.25,60,after)
    assert d2 != d and a2 == .25
    ledger.settle(d,a,.05)
    assert json.loads(ledger.path.read_text())[d2] == .25
    assert ist_date(after) == '2026-10-28'


def test_upload(tmp_path):
    path = tmp_path/'movie.mp4'
    path.write_bytes(b'media')
    assert validate_upload(path,lambda p:(120,True)) == 120
    for duration in (0,121,float('nan')):
        with pytest.raises(ValueError,match='120 seconds'):
            validate_upload(path,lambda p:(duration,True))
    with path.open('wb') as f:
        f.truncate(50*1024*1024+1)
    with pytest.raises(ValueError,match='50 MB'):
        validate_upload(path)
    with pytest.raises(ValueError,match='types'):
        validate_upload(tmp_path/'bad.html')
    with pytest.raises(ValueError,match='first'):
        validate_upload(None)


def test_xss():
    evil = '<img src=x onerror="alert(1)">'
    step = dict(step=1,role='tool',tool_name=evil,note=evil,args={'x':evil},result={'verdict':'contradicted','x':evil},ok=False)
    rendered = trace_html({'steps':[step]})
    assert '<img' not in rendered
    assert '&lt;img' in rendered
    assert 'contradicted' in rendered
    assert 'class="trace-row failed"' in rendered
    assert 'Args</b>' not in trace_html({'steps':[step]},True)


def test_discovery(tmp_path):
    folder = tmp_path/'demo'
    folder.mkdir()
    assert discover_cached(tmp_path) == {}
    for f in ('trace.json','report.json','ad_en.vtt','ad_hi.vtt','narrated_en.mp4','narrated_hi.mp4'):
        (folder/f).write_text('{}')
    (folder/'meta.json').write_text(json.dumps({'title':'Demo','input_path':'samples/sample_kitchen.mp4'}))
    assert 'demo' in discover_cached(tmp_path)
    (folder/'meta.json').write_text(json.dumps({'input_path':'../outside.mp4'}))
    assert discover_cached(tmp_path) == {}
