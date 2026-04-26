from fastapi import APIRouter, Depends, Query
from app.core.redis_manager import manager
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/presence", tags=["presence"])


@router.get("/")
async def get_presence(
    user_ids: list[int] = Query(...),
    current_user: User = Depends(get_current_user),
):
    """
    Get online/away/offline status for a list of users.
    Example: GET /presence/?user_ids=1&user_ids=2&user_ids=3
    """
    return await manager.get_channel_presence(user_ids)


@router.put("/status")
async def set_status(
    status: str = Query(..., pattern="^(online|away|busy)$"),
    current_user: User = Depends(get_current_user),
):
    """Manually set your status. Auto-expires after 30 seconds without a heartbeat."""
    await manager.set_presence(current_user.id, status, ttl=30)
    return {"user_id": current_user.id, "status": status}