import json
import wave
from pathlib import Path
import numpy as np
import pytest
from narrate.config import load_config
from narrate.llm import extract_json, SpendGuard, BudgetExceeded, MockClient
from narrate.media import word_budget, energy_gaps, detect_gaps, timestamp, scheduled, atempo_decision, probe
from narrate.pipeline import run


@pytest.mark.parametrize('seconds,expected', [(0,0), (.2,0), (2,3), (5,10)])
def test_budget(seconds, expected):
    assert word_budget(seconds) == expected


def test_json():
    assert extract_json('<think>not JSON {}</think>```json\n{"a":1}\n```') == {'a': 1}
    with pytest.raises(ValueError):
        extract_json('bad output')


def test_guard():
    guard = SpendGuard(.01)
    guard.reserve(.009)
    with pytest.raises(BudgetExceeded):
        guard.reserve(.002)
    assert guard.spent == .009


def test_config(monkeypatch, tmp_path):
    cfg = load_config()
    assert cfg['models']['fit']['input_price'] == .06
    import yaml
    cfg['max_duration'] = 42
    path = tmp_path / 'custom.yaml'
    path.write_text(yaml.safe_dump(cfg))
    monkeypatch.setenv('NARRATE_CONFIG', str(path))
    assert load_config()['max_duration'] == 42


def test_silence(tmp_path):
    rate = 16000
    samples = np.concatenate([np.zeros(rate), .4*np.sin(np.arange(rate)*.2), np.zeros(rate*2)])
    gaps = energy_gaps(samples)
    assert [(g['start'],g['end']) for g in gaps] == [(0,1),(2,4)]
    path = tmp_path / 'sound.wav'
    with wave.open(str(path), 'wb') as w:
        w.setparams((1,2,rate,0,'NONE','not compressed'))
        w.writeframes((samples*32767).astype('<i2').tobytes())
    for fallback in (False, True):
        found = detect_gaps(path, 4, True, load_config(), force_energy=fallback)
        assert len(found) == 2
        assert abs(found[1]['start']-2) < .03
    assert detect_gaps(path, 4, False, load_config())[0]['duration'] == 4


def test_timestamps_and_schedule():
    assert timestamp(3661.234) == '01:01:01.234'
    assert timestamp(59.9999) == '00:01:00.000'
    gaps = [{'start':1,'end':3}]
    assert scheduled({'start':1.1,'end':2.9}, gaps)
    assert not scheduled({'start':.9,'end':2.9}, gaps)


@pytest.mark.parametrize('duration,available,speed,trim', [(1,2,1,False),(2.4,2,1.2,False),(3,2,1.35,True)])
def test_atempo(duration,available,speed,trim):
    assert atempo_decision(duration,available) == (speed,trim)


@pytest.mark.slow
def test_pipeline(tmp_path):
    cfg = load_config()
    cfg['tts']['backend'] = 'silent'
    progress = []
    source = Path('samples/sample_kitchen.mp4')
    report = run(source, tmp_path, client=MockClient(), config=cfg, progress=progress.append)
    assert report['status'] == 'complete'
    assert report['overlaps_with_speech'] == 0
    assert report['estimated_cost_usd'] == 0
    assert all(scheduled(c, report['gaps']) for c in report['cues'])
    for lang in ('en','hi'):
        assert abs(probe(tmp_path / f'narrated_{lang}.mp4')[0] - probe(source)[0]) < .2
        vtt = (tmp_path / f'ad_{lang}.vtt').read_text()
        assert vtt.startswith('WEBVTT\n\n')
        for block in vtt.strip().split('\n\n')[1:]:
            index, times, text = block.split('\n')
            assert int(index) > 0 and text
            start, end = times.split(' --> ')
            def sec(t):
                h,m,s = t.split(':')
                return int(h)*3600+int(m)*60+float(s)
            assert sec(start) < sec(end)
        assert (tmp_path / f'transcript_{lang}.txt').is_file()
    assert json.loads((tmp_path/'report.json').read_text())['mock']
    assert progress[-1]['status'] == 'finished'


def test_ultra_failure(tmp_path):
    class BrokenUltra(MockClient):
        def call(self, stage, data, media=None):
            if stage == 'edit':
                raise ValueError('broken')
            return super().call(stage,data,media)
    cfg = load_config()
    cfg['tts']['backend'] = 'silent'
    result = run('samples/sample_kitchen.mp4',tmp_path,client=BrokenUltra(),config=cfg)
    assert result['status'] == 'complete'
    assert 'unavailable' in ' '.join(result['issues'])
    assert (tmp_path/'ad_hi.vtt').read_text() == 'WEBVTT\n\n'


def test_budget_failure_report(tmp_path):
    class Expensive(MockClient):
        def call(self, *args, **kwargs):
            self.guard.reserve(1)
    with pytest.raises(BudgetExceeded):
        run('samples/sample_kitchen.mp4',tmp_path,client=Expensive(),budget=.01)
    assert json.loads((tmp_path/'report.json').read_text())['status'] == 'budget_exceeded'


def test_frame_grid():
    from narrate.perception import frame_grids
    import base64
    import io
    from PIL import Image
    media = frame_grids('samples/sample_kitchen.mp4', [0, 3])
    raw = base64.b64decode(media[0]['image_url']['url'].split(',')[1])
    assert Image.open(io.BytesIO(raw)).size == (960, 204)


@pytest.mark.parametrize('has_audio', [True, False])
def test_no_gap_and_no_audio(tmp_path, has_audio):
    from narrate.media import ffmpeg
    source = tmp_path/'tiny.mp4'
    args = ['-f','lavfi','-i','color=blue:s=160x90:r=10:d=2']
    if has_audio:
        args += ['-f','lavfi','-i','sine=frequency=440:duration=2','-c:a','aac']
    ffmpeg(*args,'-c:v','libx264','-t',2,source)
    cfg = load_config()
    cfg['tts']['backend'] = 'silent'
    report = run(source,tmp_path/'out',client=MockClient(),config=cfg)
    assert report['overlaps_with_speech'] == 0
    assert bool(report['cues']) is not has_audio
    assert abs(probe(tmp_path/'out/narrated_en.mp4')[0]-2) < .2


def test_fit_retry_truncation(tmp_path):
    class Verbose(MockClient):
        def call(self, stage, data, media=None):
            result = super().call(stage, data, media)
            if stage == 'fit':
                for c in result['cues']:
                    c['en'] = 'word ' * 100
            return result
    cfg = load_config()
    cfg['tts']['backend'] = 'silent'
    result = run('samples/sample_kitchen.mp4',tmp_path,client=Verbose(),config=cfg)
    assert sum(u['stage']=='fit' for u in result['usage']) == 2
    assert any('Truncated' in s for s in result['issues'])
    assert all(len(c['en'].split()) <= c['budget'] for c in result['cues'])
