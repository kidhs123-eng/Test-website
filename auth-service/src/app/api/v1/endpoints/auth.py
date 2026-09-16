import secrets
from typing import Optional
from urllib.parse import urlencode
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from pwdlib import PasswordHash
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_auth_service, get_current_user, get_http_client
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import LoginSchema, RegisterSchema, TokenSchema, SetPasswordSchema
from app.schemas.user import UserResponseSchema
from app.services.auth import AuthService
from app.core.database import get_db

router = APIRouter(prefix="/auth", tags=["Auth"])
limiter = Limiter(key_func=get_remote_address)
password_hash = PasswordHash.recommended()


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Attach HttpOnly Cookie containing Refresh token."""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/api/v1/auth/refresh",
    )


@router.post("/register", response_model=TokenSchema, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def register(
    request: Request,
    response: Response,
    payload: RegisterSchema,
    service: AuthService = Depends(get_auth_service),
):
    access_token, refresh_token = await service.register(payload)
    set_refresh_cookie(response, refresh_token)
    return TokenSchema(access_token=access_token, token_type="bearer")


@router.post("/login", response_model=TokenSchema)
@limiter.limit("60/minute")
async def login(
    request: Request,
    response: Response,
    payload: LoginSchema,
    service: AuthService = Depends(get_auth_service),
):
    access_token, refresh_token = await service.login(payload)
    set_refresh_cookie(response, refresh_token)
    return TokenSchema(access_token=access_token, token_type="bearer")


@router.post("/refresh", response_model=TokenSchema)
async def refresh_tokens(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    service: AuthService = Depends(get_auth_service),
):
    access_token, new_refresh_token = await service.refresh_tokens(refresh_token)
    set_refresh_cookie(response, new_refresh_token)
    return TokenSchema(access_token=access_token, token_type="bearer")


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="refresh_token", path="/api/v1/auth/refresh", httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,)
    return {"detail": "Successfully logged out"}


@router.get("/google/login")
async def google_login():
    """Initiate Google OAuth 2.0 flow with CSRF state protection."""
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    response = RedirectResponse(url=google_auth_url)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        max_age=300,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str,
    state: str = Query(...),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    service: AuthService = Depends(get_auth_service),
):
    saved_state = request.cookies.get("oauth_state")
    if not saved_state or not secrets.compare_digest(saved_state, state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state parameter",
        )

    try:
        token_response = await http_client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            },
        )
        token_response.raise_for_status()
        google_access_token = token_response.json().get("access_token")

        userinfo_response = await http_client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {google_access_token}"},
        )
        userinfo_response.raise_for_status()
        email = userinfo_response.json().get("email")
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to communicate with Google OAuth service",
        )

    access_token, refresh_token, _ = await service.login_or_create_google_user(email=email)

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    set_refresh_cookie(response, refresh_token)
    response.delete_cookie(key="oauth_state")
    return response


@router.get("/me", response_model=UserResponseSchema)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/set-password")
async def set_password(
        data: SetPasswordSchema,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    if len(data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long",
        )

    # Хэшируем новый пароль через Argon2 (pwdlib)
    current_user.password_hash = password_hash.hash(data.new_password)

    await db.commit()
    await db.refresh(current_user)

    return {"detail": "Password successfully set"}