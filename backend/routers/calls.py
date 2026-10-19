import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.services.dispatch import create_room_and_dispatch
from backend.services.tokens import mint_customer_token
from storage.db import get_session
from storage.models import Agent, Call

router = APIRouter(prefix="/calls", tags=["calls"])

# How long to wait for the dispatched worker to actually join and mark the
# call "active" before giving up. Agent dispatch creation succeeds even when
# no worker is registered for `support-agent` (LiveKit queues the job rather
# than erroring), so without this wait a stopped worker would leave the call
# stuck "created" forever with a 201 response that looked like success.
WORKER_JOIN_TIMEOUT_S = 10
WORKER_JOIN_POLL_INTERVAL_S = 0.5


async def _wait_for_worker(session: Session, call_id: int) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + WORKER_JOIN_TIMEOUT_S
    while loop.time() < deadline:
        session.expire_all()
        call = session.get(Call, call_id)
        if call is not None and call.status == "active":
            return True
        await asyncio.sleep(WORKER_JOIN_POLL_INTERVAL_S)
    return False


class CallCreate(BaseModel):
    agent_id: int


class CallCreateOut(BaseModel):
    call_id: int
    room: str
    token: str
    livekit_url: str


class CallOut(BaseModel):
    id: int
    agent_id: int
    room_name: str
    status: str

    model_config = {"from_attributes": True}


@router.post("", response_model=CallCreateOut, status_code=201)
async def create_call(payload: CallCreate, session: Session = Depends(get_session)) -> CallCreateOut:
    agent = session.get(Agent, payload.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    call = Call(agent_id=agent.id, room_name="", status="created")
    session.add(call)
    session.flush()
    call.room_name = f"call-{call.id}"
    session.commit()
    session.refresh(call)

    metadata = json.dumps({"call_id": call.id, "agent_id": agent.id})
    try:
        await create_room_and_dispatch(call.room_name, metadata)
    except Exception as exc:
        call.status = "failed"
        session.commit()
        raise HTTPException(status_code=502, detail=f"failed to dispatch agent: {exc}") from exc

    if not await _wait_for_worker(session, call.id):
        call.status = "failed"
        session.commit()
        raise HTTPException(
            status_code=503,
            detail="no agent worker joined the call in time (is the worker running?)",
        )

    token = mint_customer_token(call.room_name, identity=f"customer-{call.id}")
    livekit_url = os.environ["LIVEKIT_URL"]
    return CallCreateOut(call_id=call.id, room=call.room_name, token=token, livekit_url=livekit_url)


@router.get("/{call_id}", response_model=CallOut)
def get_call(call_id: int, session: Session = Depends(get_session)) -> Call:
    call = session.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="call not found")
    return call
