"""Routers package."""
from app.routers.agents import router as agents_router
from app.routers.web import router as web_router

__all__ = ["agents_router", "web_router"]
