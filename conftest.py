import pytest


@pytest.fixture(autouse=True)
def _disable_event_log(monkeypatch):
    """Auto-patch init_event_log for every test to keep logs/ clean."""
    import pipeline
    monkeypatch.setattr(pipeline, "init_event_log", lambda: None)
