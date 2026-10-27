"""Token Factory (nebius) readiness checks; fully offline."""
from types import SimpleNamespace as NS
import subprocess, sys
import pytest
from narrate.config import load_config, resolve_provider
from narrate.llm import Client


def test_nebius_models_and_base_url():
    cfg = resolve_provider(load_config(), 'nebius')
    assert cfg['key_env'] == 'NEBIUS_API_KEY'
    assert cfg['base_url'].startswith('https://api.tokenfactory.nebius.com/v1')
    ids = {k: v['id'] for k, v in cfg['models'].items()}
    assert ids['perceive'] == 'nvidia/Nemotron-3.5-Super-VL'
    assert ids['orchestrate'] == 'nvidia/Nemotron-3-Ultra-550b-a55b'
    assert ids['fit'] == 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'
    assert cfg['models']['fit']['input_price'] == 0.06


def test_nebius_base_url_env_override(monkeypatch):
    monkeypatch.setenv('NARRATE_BASE_URL_NEBIUS', 'https://api.tokenfactory.us-central1.nebius.com/v1/')
    assert 'us-central1' in resolve_provider(load_config(), 'nebius')['base_url']


def test_nebius_client_uses_key_env_and_url(monkeypatch):
    monkeypatch.setenv('NEBIUS_API_KEY', 'fake-test-credential')
    seen = {}
    def factory(**kw):
        seen.update(kw)
        def create(**req):
            seen['model'] = req['model']
            return NS(usage=NS(prompt_tokens=10, completion_tokens=5), choices=[NS(message=NS(content='{"cues":[]}'))])
        return NS(chat=NS(completions=NS(create=create)))
    client = Client(resolve_provider(load_config(), 'nebius'), sdk_factory=factory)
    assert client.call('fit', {}) == {'cues': []}
    assert seen['api_key'] == 'fake-test-credential'
    assert seen['base_url'].startswith('https://api.tokenfactory.nebius.com')
    assert seen['model'] == 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'


def test_missing_key_fails_fast(monkeypatch, tmp_path):
    monkeypatch.delenv('NEBIUS_API_KEY', raising=False)
    from narrate.agent import run_agent
    with pytest.raises(RuntimeError, match='NEBIUS_API_KEY'):
        run_agent('samples/sample_kitchen.mp4', tmp_path / 'x', provider='nebius')
    env = {k: v for k, v in __import__('os').environ.items() if k != 'NEBIUS_API_KEY'}
    r = subprocess.run([sys.executable, '-m', 'narrate', 'agent', 'samples/sample_kitchen.mp4', '--out', str(tmp_path / 'y'), '--provider', 'nebius'], capture_output=True, text=True, env=env)
    assert r.returncode == 2 and 'NEBIUS_API_KEY' in r.stderr
