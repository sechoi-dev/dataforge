from app.core.config import Settings


def test_settings_use_dataforge_prefix(monkeypatch: object) -> None:
    # pytest's MonkeyPatch is intentionally avoided in the public signature for strict mypy.
    from pytest import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    monkeypatch.setenv("DATAFORGE_ENVIRONMENT", "test")
    assert Settings().environment == "test"
