"""Hugging Face Space launcher. Secrets remain server-side and are never printed."""
import os
import sys
import types
from pathlib import Path

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ.setdefault("NARRATE_DAILY_CAP_USD", "1.5")
os.environ.setdefault("NARRATE_MAX_CLIP_S", "60")

# Map the deployment-facing name to the cap hook already supported by app.app.
os.environ.setdefault("NARRATE_UI_DAILY_CAP", os.environ["NARRATE_DAILY_CAP_USD"])

# The Space entrypoint is also named app.py. Register the repository's app/
# directory as a package so importing app.app cannot resolve back to this file.
package = types.ModuleType("app")
package.__path__ = [str(Path(__file__).resolve().parent / "app")]
sys.modules["app"] = package

from app.app import main


if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--host", "0.0.0.0", "--port", "7860"]
    main()

