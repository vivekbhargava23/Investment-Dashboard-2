import pytest

from app.config import Settings


def test_settings_defaults_with_no_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    # Prevent pydantic-settings from reading any .env file
    monkeypatch.setenv("APP_ENV", "test")
    # Clear any keys that might be set in the real environment
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("PORTFOLIO_JSON_PATH", raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.finnhub_api_key is None
    assert settings.alpha_vantage_api_key is None
    assert settings.app_env == "test"
    assert settings.portfolio_json_path == "data/portfolio.json"


def test_settings_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test_key_123")
    monkeypatch.setenv("PORTFOLIO_JSON_PATH", "data/test.json")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.finnhub_api_key == "test_key_123"
    assert settings.portfolio_json_path == "data/test.json"
