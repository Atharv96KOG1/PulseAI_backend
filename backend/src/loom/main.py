import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from loom import config
from loom.api.routes import router
from loom.db import init_db
from loom.rag.vector_store import init_vector_db

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger("loom.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_vector_db()
    yield


app = FastAPI(title="Loom API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.middleware("http")
async def add_timing(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    logger.info("%s %s completed in %.2fms", request.method, request.url.path, elapsed_ms)
    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
