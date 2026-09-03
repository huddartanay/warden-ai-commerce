from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Warden",
        description=(
            "Deterministic trust and authorization layer between AI buyer agents "
            "and Razorpay payment infrastructure."
        ),
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/")
    def root() -> dict:
        return {
            "name": "Warden",
            "version": app.version,
            "docs": "/docs",
            "health": {"live": "/health/live", "ready": "/health/ready"},
        }

    return app


app = create_app()
