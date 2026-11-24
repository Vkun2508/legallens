import pytest


@pytest.fixture(autouse=True)
def _no_real_ai(monkeypatch):
    """Tests never reach the Claude API: without a key, audits use the keyword checker."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("LEGALLENS_UNFAIR_MODEL", raising=False)
