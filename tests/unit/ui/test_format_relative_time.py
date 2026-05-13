from datetime import UTC, datetime, timedelta

from app.ui.format import format_relative_time


def test_format_relative_time_unknown() -> None:
    assert format_relative_time(None) == "unknown"


def test_format_relative_time_just_now() -> None:
    assert format_relative_time(datetime.now(UTC) - timedelta(seconds=30)) == "just now"


def test_format_relative_time_minutes() -> None:
    assert format_relative_time(datetime.now(UTC) - timedelta(minutes=5)) == "5m ago"


def test_format_relative_time_hours() -> None:
    assert format_relative_time(datetime.now(UTC) - timedelta(hours=3)) == "3h ago"


def test_format_relative_time_days() -> None:
    assert format_relative_time(datetime.now(UTC) - timedelta(days=2)) == "2d ago"
