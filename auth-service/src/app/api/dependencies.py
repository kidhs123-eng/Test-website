from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.services.auth import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Retrieve shared application httpx.AsyncClient instance."""
    return request.app.state.http_client


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """Instantiate AuthService with active database session."""
    return AuthService(db_session=db)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode token and verify existence
    payload = decode_token(token)
    print(f"DEBUG TOKEN PAYLOAD: {payload}")

    if payload is None:
        raise credentials_exception

    # Verify token type
    if payload.get("type") != "access":
        raise credentials_exception

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    user = await db.get(User, int(user_id))
    if not user:
        raise credentials_exception

    return user