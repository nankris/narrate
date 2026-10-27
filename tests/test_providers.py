from types import SimpleNamespace as NS
import json
import pytest
from narrate.config import load_config, resolve_provider
from narrate.llm import Client, RateLimiter, estimate_tokens
from narrate.perception import validate_events, perceive
from narrate.pipeline import run, apply_edits


def test_resolution(monkeypatch):
    monkeypatch.setenv('NARRATE_BASE_URL_NVIDIA_DEV', 'https://example.invalid/v1')
    cfg = resolve_provider(load_config(), 'nvidia-dev')
    assert cfg['base_url'] == 'https://example.invalid/v1'
    assert cfg['rpm'] == 40
    assert cfg['models']['fit']['id'] == 'nvidia/nemotron-3.5-lightning-30b-a3b'
    cfg['providers']['nebius']['models']['fit'] = {'id':'alternate','json_mode':False,'base_url':'https://region.invalid/v1'}
    assert resolve_provider(cfg, 'nebius')['models']['fit']['json_mode'] is False


def test_missing_provider(monkeypatch, tmp_path):
    monkeypatch.delenv('NVIDIA_DEV_API_KEY', raising=False)
    cfg = load_config()
    cfg['tts']['backend'] = 'silent'
    with pytest.raises(RuntimeError, match='strict'):
        run('samples/sample_kitchen.mp4', tmp_path/'strict', provider='nvidia-dev', strict=True, config=cfg)
    with pytest.warns(UserWarning, match='MOCK'):
        report = run('samples/sample_kitchen.mp4', tmp_path/'mock', provider='nvidia-dev', config=cfg)
    assert report['provider'] == 'mock' and report['requested_provider'] == 'nvidia-dev'
    assert report['would_be_token_factory_cost_usd'] > 0
    assert report['estimated_cost_usd'] == 0


def test_media_estimate():
    content = [{'type':'text','text':'abc'*10}, {'type':'video_url','video_url':{'url':'x'*1_000_000}}, {'type':'image_url','image_url':{'url':'x'*1_000_000}}]
    assert estimate_tokens(content, 120, {}) == 37810
    assert estimate_tokens(content, 4, {'image_tokens':100,'video_tokens_per_second':10}) == 150


def test_limiter():
    now, waits = [0], []
    def sleep(delay):
        waits.append(delay)
        now[0] += delay
    limiter = RateLimiter(40, lambda:now[0], sleep)
    limiter.wait(); limiter.wait(); limiter.wait()
    assert waits == [1.5,1.5]


def test_json_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv('NEBIUS_API_KEY', 'fake-test-credential')
    calls = []
    class BadRequest(Exception):
        status_code = 400
    def create(**kwargs):
        calls.append(kwargs)
        if 'response_format' in kwargs:
            raise BadRequest('response_format unsupported')
        return NS(usage=NS(prompt_tokens=100,completion_tokens=20), choices=[NS(message=NS(content='<think>ignore {}</think>```json\n{"cues":[]}\n```'))])
    cfg = load_config()
    cfg['extra_body_thinking'] = True
    client = Client(cfg, sdk_factory=lambda **kw:NS(chat=NS(completions=NS(create=create))))
    client.raw_dir = tmp_path
    assert client.call('fit', {}) == {'cues':[]}
    client.call('fit', {})
    assert len(calls) == 3
    assert 'response_format' not in calls[-1]
    assert '/no_think' in calls[0]['messages'][0]['content']
    assert calls[0]['extra_body']['chat_template_kwargs']['enable_thinking'] is False
    assert calls[0]['max_tokens'] == 2000
    assert (tmp_path/'fit_1.txt').stat().st_size <= 4096


def test_partial_edit():
    cues = [{'id':i,'en':'Nano text','budget':5,'hi_budget':5} for i in range(3)]
    issues = []
    apply_edits(cues, {0:{'en':'Polished text','hi':'लाल आकृति दिखती है।'},1:{'en':'too many words '*10,'hi':'transliterated hindi'}}, issues)
    assert cues[0]['en'] == 'Polished text' and cues[0]['hi']
    assert cues[1]['en'] == cues[2]['en'] == 'Nano text'
    assert 'hi' not in cues[1] and 'hi' not in cues[2]


def test_lenient_events():
    good = {'t_start':'1.5','t_end':'99','importance':'3','who':'shape','action':'moves','on_screen_text':''}
    events, dropped = validate_events({'events':[good, {}, {**good,'t_start':'nan'}, {**good,'t_end':'inf'}]}, 5)
    assert len(events) == 1 and dropped == 3
    assert events[0]['t_start'] == 1.5 and events[0]['t_end'] == 5


def test_auto_zero_events(monkeypatch, tmp_path):
    import narrate.perception as module
    def ffmpeg(*args):
        args[-1].write_bytes(b'fake video')
    monkeypatch.setattr(module, 'ffmpeg', ffmpeg)
    monkeypatch.setattr(module, 'frame_grids', lambda *a: [{'type':'image_url'}])
    class Fake:
        mock = False
        count = 0
        def call(self, stage, data, media=None):
            self.count += 1
            return {'events':[] if self.count == 1 else [{'t_start':0,'t_end':2,'who':'shape','action':'moves','on_screen_text':'','importance':3}]}
    client = Fake()
    events, strategy, fallback = perceive(tmp_path/'input.mp4',tmp_path,4,load_config(),client)
    assert events and strategy == 'frames' and fallback
    assert 'Zero valid' in client.perception_details['perception_error']


def test_separate_frames_limit(monkeypatch):
    import narrate.perception as module
    monkeypatch.setattr(module, 'ffmpeg', lambda *a:NS(stdout=b'fake image'))
    parts = module.separate_frames('unused', list(range(100)))
    assert sum(p['type']=='image_url' for p in parts) == 16
    assert parts[0]['text'] == 'Frame at 0 seconds'
    assert parts[-2]['text'] == 'Frame at 99 seconds'


def test_sanitized_error():
    from narrate.llm import sanitize
    class Error(Exception):
        status_code = 401
    message = sanitize(Error('Authorization: bearer sensitive data:video/base64,secret'))
    assert message == 'Error HTTP 401'


def test_configured_default_and_mock(monkeypatch, tmp_path):
    cfg = load_config()
    cfg['default_provider'] = 'mock'
    assert resolve_provider(cfg)['provider'] == 'mock'
    # Explicit mock never needs a provider SDK or credentials, even under strict.
    cfg['tts']['backend'] = 'silent'
    report = run('samples/sample_kitchen.mp4', tmp_path, config=cfg, strict=True)
    assert report['provider'] == 'mock'
    assert all(u['mock'] and u['input_tokens'] > 0 for u in report['usage'])
    assert report['cues'][0]['assigned_event_indices'] == [0]


def test_cached_prices_and_normalization():
    from narrate.llm import usage_cost, extract_json
    u=NS(prompt_tokens=1000,completion_tokens=100,prompt_tokens_details=NS(cached_tokens=800))
    assert usage_cost(u,{'input_price':1,'cached_input_price':.12,'output_price':3})==pytest.approx(.000596)
    assert extract_json('{" .Verdict":"Supported"," .Evidence":{" .TEXT":"शीर्षक"}}')['evidence']['text']=='शीर्षक'
