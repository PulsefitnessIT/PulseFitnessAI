"""Composite auth — accept the platform token OR a CRM login token.

Used by the Staffing / HR endpoints so CRM-Corporate and Membership customers
(who sign in via the CRM login rather than the main platform) can add + manage
staff and job roles from CRM ▸ Settings, with the records shared 1:1 with
Operations ▸ Staffing.

Platform requests behave EXACTLY as before: the CRM path is only attempted
when the platform token check fails, so nothing about the existing platform
auth changes.
"""
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from utils.auth import get_current_user as _platform_user

security = HTTPBearer(auto_error=False)


async def get_current_user_or_crm(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    try:
        return await _platform_user(request, credentials)
    except HTTPException:
        # Fall back to the CRM login token (same org, mirrors role +
        # allowed_site_ids from the primary user record).
        if credentials is None:
            raise
        from routes.crm_auth import get_crm_user
        return await get_crm_user(request, credentials)
