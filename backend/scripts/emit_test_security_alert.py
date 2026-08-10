"""Emit a synthetic CRITICAL security event to exercise the Real-Time Alerts
toast feed. Run: cd /app/backend && PYTHONPATH=/app/backend python scripts/emit_test_security_alert.py
"""
import asyncio

from utils.security_events import log_security_event, SEV_CRITICAL


async def main():
    await log_security_event(
        "bola_cross_tenant_denied",
        user={"id": "qa-attacker", "email": "attacker@evil.test", "role": "manager"},
        severity=SEV_CRITICAL,
        resource_type="quote",
        resource_id="q-QA-123",
        action="update",
        detail="cross-tenant write blocked (QA live toast test)",
    )
    print("critical security event emitted → should appear as a toast within 10s")


if __name__ == "__main__":
    asyncio.run(main())
