from app.ui.pages.company import _recent_cached_tickers


def test_recent_cached_tickers_returns_empty_for_missing_dir(tmp_path: object) -> None:
    from pathlib import Path

    result = _recent_cached_tickers(Path("/nonexistent_dir_xyz"))
    assert result == []
