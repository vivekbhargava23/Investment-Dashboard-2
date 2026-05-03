def test_app_package_imports() -> None:
    import app
    import app.adapters
    import app.domain
    import app.ports
    import app.services
    import app.ui

    assert app is not None
    assert app.domain is not None
    assert app.services is not None
    assert app.ports is not None
    assert app.adapters is not None
    assert app.ui is not None


def test_config_imports() -> None:
    from app.config import Settings, get_settings

    assert Settings is not None
    assert get_settings is not None
