"""Local launcher for the cached-samples hosted demo.

Live inference is opt-in and credentials stay in the server environment.
"""
import os
import sys
import types
from pathlib import Path

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def space_caps(config=None):
    """Return hosted-demo limits from config, without environment overrides."""
    if config is None:
        from narrate.config import load_config

        config = load_config()
    values = config.get("space", {})
    return {
        "daily_cap_usd": float(values.get("daily_cap_usd", 3.0)),
        "max_clip_s": float(values.get("max_clip_s", 60)),
        "max_turns": int(values.get("max_turns", 24)),
    }


def live_enabled(config=None, environ=None):
    """Enable uploads only with an explicit switch and a provider's server key."""
    environ = os.environ if environ is None else environ
    if environ.get("NARRATE_LIVE") != "1":
        return False
    if config is None:
        from narrate.config import load_config

        config = load_config()
    providers = config.get("providers", {})
    nebius = providers.get("nebius", {})
    if isinstance(nebius, dict) and environ.get(nebius.get("key_env")):
        return True
    nvidia_dev = providers.get("nvidia-dev", {})
    return bool(
        environ.get("NARRATE_ENABLE_DEV") == "1"
        and isinstance(nvidia_dev, dict)
        and environ.get(nvidia_dev.get("key_env"))
    )


def build_demo():
    """Build the samples UI and, when authorized, its capped live tab."""
    from narrate.config import load_config

    config = load_config()
    caps = space_caps(config)
    # app.py is also this entrypoint's filename, so register the repository's
    # app directory explicitly as the `app` package before importing app.app.
    package = types.ModuleType("app")
    package.__path__ = [str(ROOT / "app")]
    sys.modules["app"] = package
    from app.app import build_app

    enabled = live_enabled(config)
    if enabled:
        os.environ["NARRATE_UI_DAILY_CAP"] = str(caps["daily_cap_usd"])
        os.environ["NARRATE_UI_MAX_TURNS"] = str(caps["max_turns"])
    return build_app(include_live=enabled, max_clip_s=caps["max_clip_s"])


demo = build_demo()


if __name__ == "__main__":
    # Deliberately no share=True: this bundle is launched by its host.
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=False)
