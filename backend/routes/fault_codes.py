"""Read-only endpoint exposing the fault-code taxonomy for frontend dropdowns."""
from fastapi import APIRouter, Depends

from utils.auth import get_current_user
from constants.fault_codes import FAULT_CODE_CATEGORIES

router = APIRouter()


@router.get("/fault-codes")
async def list_fault_codes(_user: dict = Depends(get_current_user)) -> dict:
    """Return the grouped fault-code taxonomy used in the fault-log form."""
    return {"categories": FAULT_CODE_CATEGORIES}
