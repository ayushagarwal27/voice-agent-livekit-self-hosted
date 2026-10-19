from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.routers import agents, calls
from storage.db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="Voice Agent Backend", lifespan=lifespan)
app.include_router(agents.router)
app.include_router(calls.router)
