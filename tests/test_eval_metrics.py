import json
import subprocess
import sys

from scripts.eval_metrics import evaluate_report, jaccard


def fixture_report():
    cues = [
        {"id": 1, "duration": 4.0, "word_budget_en": 5, "word_budget_hi": 5,
         "en": "A red fox jumps quickly.", "hi": "लाल लोमड़ी तेज कूदती है।"},
        {"id": 2, "duration": 2.0, "word_budget_en": 3, "word_budget_hi": 3,
         "en": "Screen shows the red fox jumps quickly", "hi": "लाल लोमड़ी फिर कूदती है"},
    ]
    return {"cues": cues, "tracks": {"en": cues, "hi": cues[:1]}}


def test_metrics_flag_repetition_phrases_budget_and_parity():
    result = evaluate_report(fixture_report(), "tiny")

    assert jaccard("The red fox jumps", "A red fox jumps") == 1.0
    assert result["repeat_flags"] == [{"previous_cue_id": 1, "cue_id": 2, "jaccard": 0.667}]
    assert result["banned_phrase_flags"] == [
        {"cue_id": 2, "language": "en", "phrase": "leading Screen"}
    ]
    assert [(row["cue_id"], row["language"]) for row in result["over_budget_flags"]] == [(2, "en"), (2, "hi")]
    assert result["language_count_parity"] == {"en": 2, "hi": 1, "equal": False}
    assert result["passed"] is False


def test_cli_writes_markdown_and_json_summary(tmp_path):
    source = tmp_path / "cached" / "tiny"
    source.mkdir(parents=True)
    (source / "report.json").write_text(json.dumps(fixture_report()), encoding="utf-8")
    output = tmp_path / "eval"

    completed = subprocess.run(
        [sys.executable, "scripts/eval_metrics.py", "--input", str(source.parent), "--output", str(output)],
        check=True, capture_output=True, text=True,
    )

    summary = json.loads((output / "metrics_summary.json").read_text(encoding="utf-8"))
    markdown = (output / "metrics_tiny.md").read_text(encoding="utf-8")
    assert completed.stdout == "Evaluated 1 clips; 0 passed\n"
    assert summary["clip_count"] == 1
    assert summary["clips"][0]["clip"] == "tiny"
    assert "Overall: **FLAGGED**" in markdown
    assert "| 2 | EN | 2.000 | 7 | 3 | no |" in markdown


def test_all_banned_phrase_rules_and_boundaries():
    texts = ["We see a room.", "The camera moves.", "Title: Intro", "Screen fades.", "The video shows rain."]
    cues = [
        {"id": i, "duration": 3, "word_budget_en": 10, "word_budget_hi": 1, "en": text, "hi": "ठीक"}
        for i, text in enumerate(texts)
    ]

    result = evaluate_report({"cues": cues, "tracks": {"en": cues, "hi": cues}}, "phrases")

    assert [row["phrase"] for row in result["banned_phrase_flags"]] == [
        "we see", "camera", "literal TITLE", "leading Screen", "video shows"
    ]
