import pytest


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch):
    """Ensure tests run against safe default configuration regardless of local .env."""
    monkeypatch.setenv("ENABLE_UPLOADS", "false")
    monkeypatch.setenv("ALLOW_PUBLIC_UPLOADS", "false")
    monkeypatch.setenv("UPLOAD_PRIVACY_STATUS", "private")
    monkeypatch.setenv("SHORTS_PUBLIC", "false")
    monkeypatch.setenv("CHANNEL_PROFILE", "bytevexa")

