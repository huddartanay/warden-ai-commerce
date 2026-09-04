from fastapi import APIRouter

from app.api import agent, audit, health, warden

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(warden.router)
api_router.include_router(agent.router)
api_router.include_router(audit.router)
