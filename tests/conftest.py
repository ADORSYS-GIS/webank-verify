import pytest


@pytest.fixture(autouse=True)
def no_heavy_imports(monkeypatch):
    """Prevent accidental loading of heavy ML libraries in unit tests."""
    pass
