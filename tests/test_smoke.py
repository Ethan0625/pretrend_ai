from __future__ import annotations


def test_pretrend_config_importable() -> None:
    from pretrend import config

    assert hasattr(config, "Settings")
    assert hasattr(config, "get_settings")


def test_pretrend_observability_package_importable() -> None:
    import pretrend.observability as observability

    assert observability is not None
