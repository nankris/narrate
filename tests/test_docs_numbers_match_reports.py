"""Guard the documentation's measured numbers against cached report drift."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_docs_numbers_match_reports():
    result = subprocess.run(
        [sys.executable, "scripts/sync_numbers.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
