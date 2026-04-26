import pytest


@pytest.fixture(autouse=True)
def _disable_event_log(monkeypatch):
    """Auto-patch init_event_log for every test; reset _log_disabled to prevent cross-test bleed."""
    import pipeline
    monkeypatch.setattr(pipeline, "init_event_log", lambda: None)
    monkeypatch.setattr(pipeline, "_log_disabled", False)
