from __future__ import annotations
from fastapi import FastAPI
from .observability import RequestContextMiddleware
from .settings import APP_NAME, APP_VERSION
from .routers import public

def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME, version=APP_VERSION)
    app.add_middleware(RequestContextMiddleware)

    # Routers
    app.include_router(public.router, prefix="/v1")

    return app

app = create_app()
