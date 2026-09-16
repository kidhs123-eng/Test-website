from typing import Optional
from urllib.parse import urlencode
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
import httpx

from app.api.dependencies import get_auth_service, get_current_user
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import LoginSchema, RegisterSchema, SetPasswordSchema, TokenSchema
from app.schemas.user import UserResponseSchema
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])
limiter = Limiter(key_func=get_remote_address)


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Утилита для установки HttpOnly Cookie с Refresh токеном."""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,                                       # Защита от JS (XSS)
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, # Время жизни в секундах
        secure=settings.COOKIE_SECURE,                       # HTTPS в продакшене
        samesite=settings.COOKIE_SAMESITE,                   # CSRF защита
        path="/api/v1/auth/refresh",                         # Кука отправляется только на эндпоинт обновления
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


@router.post("/guest-login", response_model=TokenSchema)
@limiter.limit("60/minute")
async def guest_login(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    access_token, refresh_token = await service.guest_login()
    set_refresh_cookie(response, refresh_token)
    return TokenSchema(access_token=access_token, token_type="bearer")


@router.post("/refresh", response_model=TokenSchema)
async def refresh_tokens(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    service: AuthService = Depends(get_auth_service),
):
    """Обновляет Access Token по HttpOnly Cookie."""
    access_token, new_refresh_token = await service.refresh_tokens(refresh_token)
    set_refresh_cookie(response, new_refresh_token)
    return TokenSchema(access_token=access_token, token_type="bearer")


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    service: AuthService = Depends(get_auth_service),
):
    """Очищает куки и отзывает Refresh токен в БД."""
    await service.logout(refresh_token)
    response.delete_cookie(key="refresh_token", path="/api/v1/auth/refresh")
    return {"detail": "Успешный выход из системы"}


@router.get("/google/login")
async def google_login():
    """Инициализация входа через Google OAuth 2.0."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url=google_auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    service: AuthService = Depends(get_auth_service),
):
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            },
        )
        if token_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Ошибка OAuth Google")

        google_access_token = token_response.json().get("access_token")
        userinfo = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {google_access_token}"},
        )
        email = userinfo.json().get("email")

    # Получаем токены и флаг нового пользователя
    access_token, refresh_token, is_new_user = await service.login_or_create_google_user(email=email)

    # Если пользователь новый — отправляем на форму создания пароля, иначе — на дашборд
    redirect_target = "/set-password.html" if is_new_user else "/dashboard.html"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body>
        <script>
            localStorage.setItem('access_token', '{access_token}');
            window.location.href = '{redirect_target}';
        </script>
    </body>
    </html>
    """
    response = HTMLResponse(content=html_content)
    set_refresh_cookie(response, refresh_token)
    return response


@router.get("/me", response_model=UserResponseSchema)
async def get_me(request: Request, current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/set-password")
async def set_password(
    payload: SetPasswordSchema,
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    await service.set_user_password(user_id=current_user.id, new_password=payload.new_password)
    return {"detail": "Пароль успешно обновлен"}