import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cached_demo_discovers_local_runs():
    module = load_script("serve_cached_demo.py")
    runs = module.discover()
    assert "cooking_roti_0028-0148" in runs
    values = module.sample("cooking_roti_0028-0148", "ingap")
    assert all(Path(value).exists() for value in (values[0], values[1], *values[3]))
    assert len(values) == 4  # matches the four Gradio outputs: original, narrated, cues, evidence files
    assert "WEBVTT" in values[2]


def test_submission_numbers_match_reports():
    assert load_script("check_doc_numbers.py").main() == 0
