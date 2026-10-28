import importlib.util
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def load_space(monkeypatch):
    monkeypatch.delenv("NARRATE_LIVE", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_DEV_API_KEY", raising=False)
    monkeypatch.delenv("NARRATE_ENABLE_DEV", raising=False)
    monkeypatch.delenv("NARRATE_UI_DAILY_CAP", raising=False)
    monkeypatch.delenv("NARRATE_UI_MAX_TURNS", raising=False)
    spec = importlib.util.spec_from_file_location("space_entrypoint", ROOT / "space" / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tab_labels(demo):
    return {
        block.label
        for block in demo.blocks.values()
        if type(block).__name__ == "Tab"
    }


def test_entrypoint_loads_outside_repo(tmp_path):
    env = os.environ.copy()
    for name in (
        "NARRATE_LIVE", "NEBIUS_API_KEY", "NVIDIA_API_KEY",
        "NVIDIA_DEV_API_KEY", "NARRATE_ENABLE_DEV",
    ):
        env.pop(name, None)
    result = subprocess.run(
        [sys.executable, "-c", (
            "import runpy; "
            f"runpy.run_path({str(ROOT / 'space' / 'app.py')!r}, run_name='space_test')"
        )],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_samples_load(monkeypatch):
    module = load_space(monkeypatch)
    from app.app import discover_cached

    assert module.demo is not None
    assert discover_cached()
    assert tab_labels(module.demo) == {"Samples · zero cost"}


def test_live_disabled_without_env(monkeypatch):
    module = load_space(monkeypatch)
    config = {"providers": {
        "nebius": {"key_env": "HOSTED_KEY"},
        "nvidia-dev": {"key_env": "DEV_KEY"},
    }}
    assert not module.live_enabled(config, {})
    assert not module.live_enabled(config, {"NARRATE_LIVE": "1"})
    assert not module.live_enabled(config, {"HOSTED_KEY": "set"})
    assert module.live_enabled(config, {"NARRATE_LIVE": "1", "HOSTED_KEY": "set"})
    assert not module.live_enabled(config, {
        "NARRATE_LIVE": "1", "DEV_KEY": "set",
    })
    assert module.live_enabled(config, {
        "NARRATE_LIVE": "1", "NARRATE_ENABLE_DEV": "1", "DEV_KEY": "set",
    })
    assert "Run · live" not in tab_labels(module.demo)


def test_live_tab_uses_space_caps(monkeypatch):
    module = load_space(monkeypatch)
    monkeypatch.setenv("NARRATE_LIVE", "1")
    monkeypatch.setenv("NARRATE_ENABLE_DEV", "1")
    monkeypatch.setenv("NVIDIA_DEV_API_KEY", "test-placeholder")
    demo = module.build_demo()
    assert "Run · live" in tab_labels(demo)
    assert os.environ["NARRATE_UI_DAILY_CAP"] == "3.0"
    assert os.environ["NARRATE_UI_MAX_TURNS"] == "24"


def test_caps_read_from_config(monkeypatch):
    module = load_space(monkeypatch)
    assert module.space_caps({"space": {
        "daily_cap_usd": 7, "max_clip_s": 45, "max_turns": 9,
    }}) == {"daily_cap_usd": 7.0, "max_clip_s": 45.0, "max_turns": 9}
    assert module.space_caps() == {
        "daily_cap_usd": 3.0, "max_clip_s": 60.0, "max_turns": 24,
    }
