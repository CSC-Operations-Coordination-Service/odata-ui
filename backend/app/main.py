"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.config import get_settings
from app.crypto import check_key
from app.db import create_db_and_tables, engine
from app.routers import endpoints, history, queries, query
from app.seed import seed_builtin_queries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("odata-ui")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail at startup rather than on the first write if the key is missing or bad.
    check_key()
    create_db_and_tables()
    with Session(engine) as session:
        added = seed_builtin_queries(session)
    if added:
        logger.info("Seeded %d built-in query templates.", added)
    yield


app = FastAPI(
    title="OData Explorer",
    description="Query configured OData interfaces from the browser.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(endpoints.router)
app.include_router(query.router)
app.include_router(queries.router)
app.include_router(history.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
