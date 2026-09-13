import secrets
from typing import Tuple
from fastapi import HTTPException, status
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.repositories.user import UserRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.schemas.auth import LoginSchema, RegisterSchema


class AuthService:
    def __init__(
        self,
        repo: UserRepository,
        session: AsyncSession,
        refresh_repo: RefreshTokenRepository | None = None,
    ):
        self.repo = repo
        self.session = session
        self.refresh_repo = refresh_repo

    def _generate_tokens(self, user_id: int, email: str) -> Tuple[str, str]:
        """Вспомогательный метод для генерации пары Access и Refresh токенов."""
        access_token = create_access_token(
            data={"sub": str(user_id), "email": email}
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user_id), "email": email}
        )
        return access_token, refresh_token

    async def register(self, payload: RegisterSchema) -> Tuple[str, str]:
        existing_user = await self.repo.get_by_email(payload.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким email уже зарегистрирован.",
            )

        hashed_pw = hash_password(payload.password)
        user = await self.repo.create(
            email=payload.email, password_hash=hashed_pw
        )
        await self.session.commit()
        await self.session.refresh(user)

        return self._generate_tokens(user.id, user.email)

    async def login(self, payload: LoginSchema) -> Tuple[str, str]:
        user = await self.repo.get_by_email(payload.email)

        # Защита от None в password_hash (для пользователей OAuth/Гостей)
        if (
            not user
            or not user.password_hash
            or not verify_password(payload.password, user.password_hash)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный email или пароль.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return self._generate_tokens(user.id, user.email)

    async def guest_login(self) -> Tuple[str, str]:
        guest_email = f"guest_{secrets.token_hex(6)}@system.local"

        temp_password = secrets.token_hex(8)
        guest_user = await self.repo.create(
            email=guest_email,
            password_hash=temp_password,
        )
        await self.session.commit()
        await self.session.refresh(guest_user)

        return self._generate_tokens(guest_user.id, guest_user.email)

    async def login_or_create_google_user(
        self, email: EmailStr
    ) -> Tuple[str, str, bool]:
        user = await self.repo.get_by_email(email)
        is_new_user = False

        if not user:
            temp_password = secrets.token_hex(8)
            user = await self.repo.create(email=email, password_hash=temp_password)
            await self.session.commit()
            await self.session.refresh(user)
            is_new_user = True

        access_token, refresh_token = self._generate_tokens(user.id, user.email)
        return access_token, refresh_token, is_new_user

    async def refresh_tokens(
        self, refresh_token: str | None
    ) -> Tuple[str, str]:
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh токен не предоставлен",
            )

        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Недействительный или просроченный refresh токен",
            )

        user_id = payload.get("sub")
        email = payload.get("email")

        if not user_id or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Некорректный payload токена",
            )

        user = await self.repo.get_by_id(int(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден",
            )

        return self._generate_tokens(user.id, user.email)

    async def logout(self, refresh_token: str | None) -> None:
        if self.refresh_repo and refresh_token:
            await self.refresh_repo.revoke_token(refresh_token)
            await self.session.commit()

    async def set_user_password(self, user_id: int, new_password: str) -> None:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден",
            )

        pwd_hash = hash_password(new_password)
        await self.repo.update_password(user, pwd_hash)
        await self.session.commit()