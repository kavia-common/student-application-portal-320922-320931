from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.core.config import get_settings
from src.api.routes.admin import router as admin_router
from src.api.routes.applications import router as applications_router
from src.api.routes.auth import router as auth_router
from src.api.routes.notifications import router as notifications_router

settings = get_settings()

openapi_tags = [
    {"name": "Auth", "description": "JWT authentication and user identity endpoints."},
    {
        "name": "Student Applications",
        "description": "Student CRUD + submission workflow for applications.",
    },
    {
        "name": "Admin",
        "description": "Admin review endpoints: list/filter/detail, status transitions, notes.",
    },
    {"name": "Notifications", "description": "In-app notification log endpoints."},
]

app = FastAPI(
    title="Student Application Portal API",
    description=(
        "Backend API for student application submission and admin review.\n\n"
        "Auth uses OAuth2 password flow with Bearer JWTs.\n"
        "Include header: `Authorization: Bearer <token>`."
    ),
    version="1.0.0",
    openapi_tags=openapi_tags,
)

# CORS: env-driven (default '*', good for dev)
allow_origins = (
    [o.strip() for o in settings.cors_allow_origins.split(",")]
    if settings.cors_allow_origins
    else ["*"]
)

# Note: If allow_credentials=True, browsers will reject wildcard allow-origin ("*").
# Starlette handles this by echoing back the request Origin for allowed requests
# when "*" is configured; that's OK for local dev/preview.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/",
    summary="Health check",
    description="Returns a simple health response. Does not check DB connectivity.",
)
def health_check():
    return {"message": "Healthy"}


@app.get(
    "/health/db",
    summary="Database health check",
    description="Performs a simple DB connectivity check (SELECT 1).",
)
def db_health_check() -> dict:
    """DB connectivity check.

    Returns:
        {"ok": True} when DB is reachable.
        {"ok": False, "error": "..."} with 500 status when unreachable.

    This endpoint is intended for integration verification across containers and should
    provide actionable error text when DB env/credentials are misconfigured.
    """
    from fastapi import HTTPException
    from sqlalchemy import text

    # Lazy import to avoid import cycles at module load time.
    from src.api.core.db import SessionLocal

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "ok": False,
                "error": str(e),
                "hint": "Check POSTGRES_URL / POSTGRES_USER / POSTGRES_PASSWORD and DB port.",
            },
        ) from e


app.include_router(auth_router)
app.include_router(applications_router)
app.include_router(admin_router)
app.include_router(notifications_router)
