"""Tests for the production secrets guard."""

import pytest

from app.core.config import Settings


def test_dev_allows_default_secrets():
    Settings(environment="development").validate_secrets()  # must not raise


def test_production_rejects_default_secrets():
    s = Settings(environment="production")  # all secrets left at insecure defaults
    with pytest.raises(RuntimeError):
        s.validate_secrets()


def test_production_allows_real_secrets():
    Settings(
        environment="production",
        kyc_api_key="real-key",
        admin_secret="real-admin",
        webhook_secret="real-webhook",
    ).validate_secrets()  # must not raise
