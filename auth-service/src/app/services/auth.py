from typing import Tuple
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginSchema, RegisterSchema


class AuthService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def register(self, payload: RegisterSchema) -> Tuple[str, str]:
        """Register new user using standard email/password authentication."""
        existing_user = await self.get_user_by_email(payload.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists",
            )

        new_user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            auth_provider="email",
        )
        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)

        return self._generate_tokens(new_user.id)

    async def login(self, payload: LoginSchema) -> Tuple[str, str]:
        """Authenticate user using email and password."""
        user = await self.get_user_by_email(payload.email)

        if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        return self._generate_tokens(user.id)

    async def login_or_create_google_user(self, email: str) -> Tuple[str, str, bool]:
        """Authenticate or register user via Google OAuth 2.0."""
        user = await self.get_user_by_email(email)
        is_new_user = False

        if not user:
            user = User(
                email=email,
                password_hash=None,
                auth_provider="google",
            )
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            is_new_user = True

        access_token, refresh_token = self._generate_tokens(user.id)
        return access_token, refresh_token, is_new_user

    async def refresh_tokens(self, refresh_token: str | None) -> Tuple[str, str]:
        """Validate refresh token and issue a new token pair."""
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is missing",
            )

        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        user_id = payload.get("sub")
        user = await self.get_user_by_id(int(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User associated with token not found",
            )

        return self._generate_tokens(user.id)

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def get_user_by_id(self, user_id: int) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    def _generate_tokens(self, user_id: int) -> Tuple[str, str]:
        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token(user_id)
        return access_token, refresh_token