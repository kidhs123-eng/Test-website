from typing import List
from fastapi import APIRouter, Depends
from app.api.dependencies import get_user_repository
from app.repositories.user import UserRepository
from app.schemas.user import UserResponseSchema

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserResponseSchema])
async def list_users(
    limit: int = 10,
    offset: int = 0,
    repo: UserRepository = Depends(get_user_repository),
):
    users = await repo.get_all(limit=limit, offset=offset)
    return users