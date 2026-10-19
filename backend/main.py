from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.routers import agents, calls
from storage.db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="Voice Agent Backend", lifespan=lifespan)
app.include_router(agents.router)
app.include_router(calls.router)

# Mounted last and matched only after the routes above, so /agents and /calls
# are never shadowed by the catch-all static mount (AGENTS.md: plain static
# files served by FastAPI so there is no CORS).
app.mount("/", StaticFiles(directory="web", html=True), name="web")
