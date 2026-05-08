"""Iter 215ae — Secrets audit unit tests."""
from unittest.mock import patch

from utils import secrets_audit


def _env(monkeypatch, **kv):
    for k, v in kv.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


def test_all_good_passes(monkeypatch):
    _env(monkeypatch,
         JWT_SECRET="a" * 64,
         STRIPE_API_KEY="sk_test",
         STRIPE_WEBHOOK_SECRET="whsec_abc",
         CORS_ORIGINS="https://example.com",
         MASTER_ADMIN_PASSWORD="SomeStrongPw!0nly",
         APP_ENV="production")
    assert secrets_audit._findings() == []


def test_short_jwt_secret_flagged(monkeypatch):
    _env(monkeypatch, JWT_SECRET="short", STRIPE_API_KEY=None,
         STRIPE_WEBHOOK_SECRET=None, CORS_ORIGINS="", APP_ENV=None,
         MASTER_ADMIN_PASSWORD=None)
    findings = secrets_audit._findings()
    assert any(f["key"] == "JWT_SECRET" and f["severity"] == "critical" for f in findings)


def test_weak_jwt_secret_needle_flagged(monkeypatch):
    _env(monkeypatch,
         JWT_SECRET="gymaxis-ai-secret-key-2026" + "x" * 50,  # long but contains needle
         STRIPE_API_KEY=None, STRIPE_WEBHOOK_SECRET=None,
         CORS_ORIGINS="", APP_ENV=None, MASTER_ADMIN_PASSWORD=None)
    findings = secrets_audit._findings()
    assert any("known-weak substring" in f["message"] for f in findings)


def test_missing_stripe_webhook_secret_flagged(monkeypatch):
    _env(monkeypatch,
         JWT_SECRET="a" * 64, STRIPE_API_KEY="sk_live_x",
         STRIPE_WEBHOOK_SECRET=None, CORS_ORIGINS="https://x.com",
         APP_ENV=None, MASTER_ADMIN_PASSWORD=None)
    findings = secrets_audit._findings()
    assert any(f["key"] == "STRIPE_WEBHOOK_SECRET" for f in findings)


def test_cors_wildcard_only_flagged_in_prod(monkeypatch):
    # Dev → no finding
    _env(monkeypatch, JWT_SECRET="a" * 64, STRIPE_API_KEY=None,
         STRIPE_WEBHOOK_SECRET=None, CORS_ORIGINS="*",
         APP_ENV="development", MASTER_ADMIN_PASSWORD=None)
    assert not any(f["key"] == "CORS_ORIGINS" for f in secrets_audit._findings())
    # Prod → flagged
    _env(monkeypatch, APP_ENV="production")
    assert any(f["key"] == "CORS_ORIGINS" for f in secrets_audit._findings())


def test_weak_admin_pw_only_flagged_in_prod(monkeypatch):
    _env(monkeypatch, JWT_SECRET="a" * 64, STRIPE_API_KEY=None,
         STRIPE_WEBHOOK_SECRET=None, CORS_ORIGINS="https://x.com",
         APP_ENV="development", MASTER_ADMIN_PASSWORD="MasterAdmin123!")
    # Dev → no finding
    assert not any(f["key"] == "MASTER_ADMIN_PASSWORD" for f in secrets_audit._findings())
    # Prod → flagged
    _env(monkeypatch, APP_ENV="production")
    findings = secrets_audit._findings()
    assert any(f["key"] == "MASTER_ADMIN_PASSWORD" for f in findings)


def test_prod_aborts_on_critical(monkeypatch):
    _env(monkeypatch, JWT_SECRET="short", STRIPE_API_KEY=None,
         STRIPE_WEBHOOK_SECRET=None, CORS_ORIGINS="https://x.com",
         APP_ENV="production", MASTER_ADMIN_PASSWORD=None)
    with patch("utils.secrets_audit.sys.exit") as exit_:
        secrets_audit.run_startup_audit()
    exit_.assert_called_once_with(2)


def test_dev_does_not_abort_on_critical(monkeypatch):
    _env(monkeypatch, JWT_SECRET="short", STRIPE_API_KEY=None,
         STRIPE_WEBHOOK_SECRET=None, CORS_ORIGINS="https://x.com",
         APP_ENV=None, MASTER_ADMIN_PASSWORD=None)
    with patch("utils.secrets_audit.sys.exit") as exit_:
        findings = secrets_audit.run_startup_audit()
    exit_.assert_not_called()
    assert findings  # still reports them
