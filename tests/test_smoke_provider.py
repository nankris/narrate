import os, subprocess, sys
from pathlib import Path
from narrate.config import load_config, resolve_provider

ROOT = Path(__file__).resolve().parents[1]


def test_model_id_env_override(monkeypatch):
    monkeypatch.setenv('NARRATE_MODEL_ORCHESTRATE', 'nvidia/nemotron-3-super-120b-a12b')
    cfg = resolve_provider(load_config(), 'nebius')
    assert cfg['models']['orchestrate']['id'] == 'nvidia/nemotron-3-super-120b-a12b'
    assert cfg['models']['perceive']['id'] == 'nvidia/Nemotron-3.5-Super-VL'


def test_smoke_provider_without_key_makes_no_calls():
    env = {k: v for k, v in os.environ.items() if k != 'NEBIUS_API_KEY'}
    r = subprocess.run([sys.executable, 'scripts/smoke_provider.py'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2
    assert 'NEBIUS_API_KEY is not set' in r.stderr + r.stdout
