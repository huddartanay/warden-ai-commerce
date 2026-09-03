from fastapi import APIRouter

from app.api import health, warden

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(warden.router)
