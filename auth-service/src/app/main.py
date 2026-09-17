from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
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
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router, prefix="/api/v1")



@app.get("/dashboard")
async def serve_dashboard(request: Request):
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/login")
async def serve_login(request: Request):
    if request.cookies.get("refresh_token"):
        print(request.cookies.get("refresh_token"), request)
        return RedirectResponse(url="/dashboard", status_code=307)
    else:
        return FileResponse(STATIC_DIR / "login.html")


@app.get("/register")
async def serve_register(request: Request):
    if request.cookies.get("refresh_token"):
        return RedirectResponse(url="/dashboard", status_code=307)
    else:
        return FileResponse(STATIC_DIR / "register.html")


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")