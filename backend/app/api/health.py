from fastapi import APIRouter

from app.db import check_database_connection

router = APIRouter()


@router.get("/health/live")
def liveness() -> dict:
    """Process is up. Independent of DB."""
    return {"status": "ok", "service": "warden-backend"}


@router.get("/health/ready")
def readiness() -> dict:
    """Ready to serve traffic: process up AND database reachable."""
    db_ok, db_error = check_database_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "warden-backend",
        "checks": {
            "database": {
                "ok": db_ok,
                "error": db_error,
            },
        },
    }
