"""Shared test helpers — keeps individual test modules slim.

Iter 216h116 — when MOD HQ users hit ``/auth/login`` they now receive a
``requires_mfa_enrolment`` step on first login (mandatory TOTP). The
helper here drives the enrolment + verification dance so tests can
treat HQ login as a single call.
"""
from __future__ import annotations

import os

import pyotp
import requests


def _api_base() -> str:
    """Resolve the backend base URL the same way conftest does."""
    from tests.conftest import _test_backend_url  # type: ignore
    return _test_backend_url() + "/api"


def _login_raw(email: str, password: str, portal: str = "mod") -> dict:
    r = requests.post(
        f"{_api_base()}/auth/login",
        json={"email": email, "password": password, "portal": portal},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def hq_login_with_mfa(email: str, password: str, portal: str = "mod") -> dict:
    """Return a /auth/login-shaped response with a real ``token`` field.

    Behaves identically to a plain ``_login`` for non-HQ users. For
    MOD HQ (mod_org / mod_branch) it transparently completes the
    mandatory MFA enrolment so the rest of the test can carry on.
    """
    from pymongo import MongoClient

    body = _login_raw(email, password, portal)
    if body.get("token"):
        return body
    if body.get("requires_mfa"):
        # Already enrolled in a previous run — wipe state and retry.
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        client = MongoClient(mongo_url)
        try:
            client[db_name].users.update_one(
                {"email": email},
                {"$set": {"mfa_enabled": False, "mfa_secret": None, "mfa_backup_codes": []}},
            )
            user_row = client[db_name].users.find_one({"email": email}, {"_id": 0, "id": 1})
            if user_row:
                client[db_name].user_mfa.delete_many({"user_id": user_row["id"]})
        finally:
            client.close()
        return hq_login_with_mfa(email, password, portal)
    if not body.get("requires_mfa_enrolment"):
        raise AssertionError(f"Unexpected /auth/login response shape: {body}")
    temp = body["temp_token"]
    setup = requests.post(
        f"{_api_base()}/auth/mfa/enrol/setup",
        json={"temp_token": temp}, timeout=15,
    )
    setup.raise_for_status()
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()
    final = requests.post(
        f"{_api_base()}/auth/mfa/enrol/complete",
        json={"temp_token": temp, "code": code}, timeout=15,
    )
    final.raise_for_status()
    return final.json()
