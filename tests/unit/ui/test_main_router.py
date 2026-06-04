"""Router tests for app.ui.main.render_page (TICKET-ROBUST-1).

The router must distinguish three cases:
  * page module exists and render() succeeds  → renders the page
  * page genuinely not built (no module / no render attr) → "Coming Soon"
  * page exists but import or render() raises  → logged + visible error surface,
    NEVER the misleading "Coming Soon" placeholder.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.ui.main as main_mod


def _set_page(monkeypatch, page_id: str) -> None:
    monkeypatch.setattr(main_mod.st, "session_state", {"current_page": page_id})


def test_render_page_renders_existing_page(monkeypatch):
    """Module file exists and exposes render() → render() is called, no fallbacks."""
    fake_module = MagicMock()
    monkeypatch.setattr(main_mod.os.path, "exists", lambda p: True)
    monkeypatch.setattr(main_mod.importlib, "import_module", lambda name: fake_module)
    placeholder = MagicMock()
    error = MagicMock()
    monkeypatch.setattr(main_mod, "render_placeholder", placeholder)
    monkeypatch.setattr(main_mod, "render_page_error", error)
    _set_page(monkeypatch, "overview")

    main_mod.render_page()

    fake_module.render.assert_called_once_with()
    placeholder.assert_not_called()
    error.assert_not_called()


def test_render_page_placeholder_when_module_file_missing(monkeypatch):
    """No module file on disk → 'Coming Soon' placeholder, no error surface."""
    monkeypatch.setattr(main_mod.os.path, "exists", lambda p: False)
    placeholder = MagicMock()
    error = MagicMock()
    monkeypatch.setattr(main_mod, "render_placeholder", placeholder)
    monkeypatch.setattr(main_mod, "render_page_error", error)
    _set_page(monkeypatch, "not_a_real_page")

    main_mod.render_page()

    placeholder.assert_called_once_with()
    error.assert_not_called()


def test_render_page_placeholder_when_no_render_attr(monkeypatch):
    """Module exists but has no render() → 'Coming Soon', not an error."""
    module_without_render = SimpleNamespace()  # no .render attribute
    monkeypatch.setattr(main_mod.os.path, "exists", lambda p: True)
    monkeypatch.setattr(main_mod.importlib, "import_module", lambda name: module_without_render)
    placeholder = MagicMock()
    error = MagicMock()
    monkeypatch.setattr(main_mod, "render_placeholder", placeholder)
    monkeypatch.setattr(main_mod, "render_page_error", error)
    _set_page(monkeypatch, "stub_page")

    main_mod.render_page()

    placeholder.assert_called_once_with()
    error.assert_not_called()


def test_render_page_error_when_render_raises(monkeypatch):
    """render() raises → error surface, NEVER the 'Coming Soon' placeholder."""
    boom = RuntimeError("kaboom")
    fake_module = MagicMock()
    fake_module.render.side_effect = boom
    monkeypatch.setattr(main_mod.os.path, "exists", lambda p: True)
    monkeypatch.setattr(main_mod.importlib, "import_module", lambda name: fake_module)
    placeholder = MagicMock()
    error = MagicMock()
    monkeypatch.setattr(main_mod, "render_placeholder", placeholder)
    monkeypatch.setattr(main_mod, "render_page_error", error)
    _set_page(monkeypatch, "tax")

    main_mod.render_page()

    error.assert_called_once_with("tax", boom)
    placeholder.assert_not_called()


def test_render_page_error_when_import_raises(monkeypatch):
    """Import raising is a real bug → error surface, not 'Coming Soon'."""
    boom = ImportError("bad import")

    def _raise(name):
        raise boom

    monkeypatch.setattr(main_mod.os.path, "exists", lambda p: True)
    monkeypatch.setattr(main_mod.importlib, "import_module", _raise)
    placeholder = MagicMock()
    error = MagicMock()
    monkeypatch.setattr(main_mod, "render_placeholder", placeholder)
    monkeypatch.setattr(main_mod, "render_page_error", error)
    _set_page(monkeypatch, "analytics")

    main_mod.render_page()

    error.assert_called_once_with("analytics", boom)
    placeholder.assert_not_called()


def test_render_page_error_dev_shows_exception_and_logs(monkeypatch, caplog):
    """In dev (app_env != 'prod') the full exception is shown and logged."""
    monkeypatch.setattr(main_mod, "get_settings", lambda: SimpleNamespace(app_env="local"))
    st_error = MagicMock()
    st_exception = MagicMock()
    monkeypatch.setattr(main_mod.st, "error", st_error)
    monkeypatch.setattr(main_mod.st, "exception", st_exception)

    exc = ValueError("detail")
    with caplog.at_level("ERROR"):
        main_mod.render_page_error("tax", exc)

    st_exception.assert_called_once_with(exc)
    st_error.assert_called_once()
    assert any("tax" in r.message or "tax" in r.getMessage() for r in caplog.records)


def test_render_page_error_prod_hides_exception(monkeypatch):
    """In prod the raw exception is NOT shown; a friendly message is."""
    monkeypatch.setattr(main_mod, "get_settings", lambda: SimpleNamespace(app_env="prod"))
    st_error = MagicMock()
    st_exception = MagicMock()
    monkeypatch.setattr(main_mod.st, "error", st_error)
    monkeypatch.setattr(main_mod.st, "exception", st_exception)

    main_mod.render_page_error("tax", ValueError("detail"))

    st_exception.assert_not_called()
    st_error.assert_called_once()
