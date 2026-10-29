import pytest

from narrate.config import load_config, resolve_provider
from narrate.llm import Client


def test_provider_call_is_blocked_by_socket_guard(monkeypatch):
    """Even an installed test credential cannot permit a provider connection."""
    monkeypatch.setenv("NEBIUS_API_KEY", "fake-test-credential")
    cfg = resolve_provider(load_config(), "nebius")
    cfg["base_url"] = "http://192.0.2.1/v1"
    for model in cfg["models"].values():
        model.pop("base_url", None)

    client = Client(cfg)
    client.retry_attempts = 1

    with pytest.raises(Exception) as caught:
        client.call("fit", {})

    errors = []
    error = caught.value
    while error is not None and error not in errors:
        errors.append(error)
        error = error.__cause__ or error.__context__
    assert any("external network access blocked" in str(error) for error in errors)
