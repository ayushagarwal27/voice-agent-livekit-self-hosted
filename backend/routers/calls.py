import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.services.dispatch import create_room_and_dispatch
from backend.services.tokens import (
    mint_customer_token,
    mint_operator_takeover_token,
    mint_operator_token,
)
from storage.db import get_session
from storage.models import Agent, Call, TranscriptLine, Whisper

router = APIRouter(prefix="/calls", tags=["calls"])


def _browser_livekit_url() -> str:
    """The address handed to a browser client, as opposed to `LIVEKIT_URL`
    itself, which `api.LiveKitAPI()` (backend/services/dispatch.py) reads
    implicitly for the backend's *own* server-to-server calls. The two only
    diverge under Stretch S2 (docker compose): inside the compose network
    LIVEKIT_URL has to be the "livekit" service name for the backend's own
    calls to resolve, but a host browser can't resolve that name, so compose
    sets LIVEKIT_PUBLIC_URL to "ws://localhost:7880" for this. Outside
    compose there's only one address, so this falls back to LIVEKIT_URL."""
    return os.environ.get("LIVEKIT_PUBLIC_URL") or os.environ["LIVEKIT_URL"]


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


class OperatorTokenOut(BaseModel):
    room: str
    token: str
    livekit_url: str


class TranscriptLineOut(BaseModel):
    seq: int
    speaker: str
    text: str
    ts_abs: datetime
    ts_ms: int
    interrupted: bool

    model_config = {"from_attributes": True}


class WhisperOut(BaseModel):
    text: str
    received_at: datetime

    model_config = {"from_attributes": True}


class CallOut(BaseModel):
    id: int
    agent_id: int
    room_name: str
    status: str
    transcript: list[TranscriptLineOut] | None = None
    compliance: dict[str, Any] | str = "pending"
    whispers: list[WhisperOut] = []

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
    livekit_url = _browser_livekit_url()
    return CallCreateOut(call_id=call.id, room=call.room_name, token=token, livekit_url=livekit_url)


@router.post("/{call_id}/operator-token", response_model=OperatorTokenOut)
def create_operator_token(call_id: int, session: Session = Depends(get_session)) -> OperatorTokenOut:
    call = session.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="call not found")

    # Suffixed so two operator tabs open on the same call don't collide on identity.
    identity = f"operator-{call_id}-{uuid.uuid4().hex[:8]}"
    token = mint_operator_token(call.room_name, identity=identity)
    livekit_url = _browser_livekit_url()
    return OperatorTokenOut(room=call.room_name, token=token, livekit_url=livekit_url)


@router.post("/{call_id}/takeover-token", response_model=OperatorTokenOut)
def create_takeover_token(call_id: int, session: Session = Depends(get_session)) -> OperatorTokenOut:
    """Minted when the operator clicks "Take over" (Stretch S1). Separate identity
    from the listen-only one, and no longer hidden -- see tokens.py."""
    call = session.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="call not found")

    identity = f"operator-takeover-{call_id}-{uuid.uuid4().hex[:8]}"
    token = mint_operator_takeover_token(call.room_name, identity=identity)
    livekit_url = _browser_livekit_url()
    return OperatorTokenOut(room=call.room_name, token=token, livekit_url=livekit_url)


@router.get("/{call_id}", response_model=CallOut)
def get_call(call_id: int, session: Session = Depends(get_session)) -> CallOut:
    call = session.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="call not found")

    transcript = None
    if call.status == "ended":
        lines = (
            session.query(TranscriptLine)
            .filter_by(call_id=call_id)
            .order_by(TranscriptLine.seq)
            .all()
        )
        transcript = [TranscriptLineOut.model_validate(line) for line in lines]

    compliance = json.loads(call.compliance_json) if call.compliance_json else "pending"

    whisper_rows = (
        session.query(Whisper)
        .filter_by(call_id=call_id)
        .order_by(Whisper.received_at)
        .all()
    )
    whispers = [WhisperOut.model_validate(row) for row in whisper_rows]

    return CallOut(
        id=call.id,
        agent_id=call.agent_id,
        room_name=call.room_name,
        status=call.status,
        transcript=transcript,
        compliance=compliance,
        whispers=whispers,
    )
