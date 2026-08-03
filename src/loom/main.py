import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from loom import config
from loom.api.deps import get_analysis_repository, get_vector_repository
from loom.api.routes import router

logging.basicConfig(level=config.LOG_LEVEL)


class LoomApplication:
    """Builds and owns the FastAPI app object: lifespan, middleware, routes."""

    def __init__(self):
        self.logger = logging.getLogger("loom.main")
        self.app = FastAPI(title="Loom API", version="0.1.0", lifespan=self._lifespan)
        self._configure_middleware()
        self._configure_routes()

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        get_analysis_repository().init_schema()
        get_vector_repository().init_schema()
        yield

    def _configure_middleware(self) -> None:
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.app.middleware("http")(self._add_timing)

    async def _add_timing(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        self.logger.info("%s %s completed in %.2fms", request.method, request.url.path, elapsed_ms)
        return response

    def _configure_routes(self) -> None:
        self.app.include_router(router)
        self.app.get("/health")(self.health)

    async def health(self) -> dict:
        return {"status": "ok"}


app = LoomApplication().app
