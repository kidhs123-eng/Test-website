from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.auth import limiter

# Dynamic base directory determination relative to main.py
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="Authentication API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router, prefix="/api/v1")


@app.get("/dashboard")
async def serve_dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/login")
async def serve_login():
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/register")
async def serve_register():
    return FileResponse(STATIC_DIR / "register.html")

@app.get("/")
async def root():
    # Автоматический редирект с главными частыми путями на dashboard
    return RedirectResponse(url="/dashboard")