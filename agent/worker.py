"""Voice agent for customer support (Phase 4: DB-driven persona).

Registers under `agent_name="support-agent"` for explicit dispatch (AGENTS.md
section 1): the worker does not auto-join every room. The backend creates a
room and an agent dispatch carrying `{call_id, agent_id}` as job metadata;
this entrypoint reads that metadata, loads the persona and call row from the
DB, and marks the call `active`/`ended` as the session starts and stops.

Usage:
  uv run -m livekit.agents download-files   # once, to fetch the VAD/turn-detector models
  uv run python agent/worker.py console      # talk to it from the terminal (mic/speakers)
  uv run python agent/worker.py dev          # join real rooms on the self-hosted LiveKit server
"""

import json
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from livekit.agents import Agent, AgentSession, JobContext, JobProcess, WorkerOptions, cli
from livekit.plugins import cartesia, deepgram, openai, silero
from livekit.plugins.turn_detector.english import EnglishModel

from agent.transcript import attach_transcript_recorder
from storage.db import SessionLocal
from storage.models import Agent as AgentRow
from storage.models import Call

load_dotenv()

AGENT_NAME = "support-agent"

GREETING = (
    "Thanks for calling Acme Telecom, this call is being recorded for quality and "
    "training. How can I help you today?"
)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


class SupportAgent(Agent):
    def __init__(self, system_prompt: str) -> None:
        super().__init__(instructions=system_prompt)

    async def on_enter(self) -> None:
        self.session.say(GREETING)


def _mark_call_status(call_id: int, status: str, *, ended: bool = False) -> None:
    db_session = SessionLocal()
    try:
        call = db_session.get(Call, call_id)
        if call is None:
            return
        call.status = status
        if ended:
            call.ended_at = datetime.now(timezone.utc)
        db_session.commit()
    finally:
        db_session.close()


async def entrypoint(ctx: JobContext) -> None:
    metadata = json.loads(ctx.job.metadata)
    call_id = metadata["call_id"]
    agent_id = metadata["agent_id"]

    db_session = SessionLocal()
    try:
        agent_row = db_session.get(AgentRow, agent_id)
        call_row = db_session.get(Call, call_id)
        if agent_row is None or call_row is None:
            raise RuntimeError(f"agent {agent_id} or call {call_id} not found in DB")
        system_prompt = agent_row.system_prompt
        voice = agent_row.voice
        model = agent_row.model
    finally:
        db_session.close()

    await ctx.connect()

    async def on_shutdown() -> None:
        _mark_call_status(call_id, "ended", ended=True)

    ctx.add_shutdown_callback(on_shutdown)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model=model),
        tts=cartesia.TTS(voice=voice),
        # mode="vad": the default ("adaptive") calls LiveKit's cloud inference
        # service for interruption detection, which this self-hosted-only
        # project does not use (rule 2).
        turn_handling={"turn_detection": EnglishModel(), "interruption": {"mode": "vad"}},
    )

    call_start_ts = time.time()
    attach_transcript_recorder(session, call_id, call_start_ts)

    await session.start(agent=SupportAgent(system_prompt), room=ctx.room)
    _mark_call_status(call_id, "active")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, agent_name=AGENT_NAME))
