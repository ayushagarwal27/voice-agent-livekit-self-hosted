"""Voice agent for customer support (Phase 4: DB-driven persona).

Registers under `agent_name="support-agent"` for explicit dispatch (AGENTS.md
section 1): the worker does not auto-join every room. The backend creates a
room and an agent dispatch carrying `{call_id, agent_id}` as job metadata;
this entrypoint reads that metadata, loads the persona and call row from the
DB, and marks the call `active`/`ended` as the session starts and stops.

Usage (module form required -- `python agent/worker.py` can't resolve the
`agent.*` absolute imports below; `-m` puts the project root on sys.path):
  uv run -m livekit.agents download-files   # once, to fetch the VAD/turn-detector models
  uv run python -m agent.worker console      # talk to it from the terminal (mic/speakers)
  uv run python -m agent.worker dev          # join real rooms on the self-hosted LiveKit server
"""

import json
import logging
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from livekit.agents import Agent, AgentSession, JobContext, JobProcess, WorkerOptions, cli
from livekit.agents.llm import ChatMessage
from livekit.agents.voice.events import ConversationItemAddedEvent
from livekit.plugins import cartesia, deepgram, openai, silero
from livekit.plugins.turn_detector.english import EnglishModel

from agent.metrics import attach_metrics_recorder
from agent.transcript import attach_transcript_recorder
from agent.whisper import attach_whisper_listener
from compliance.runner import run_compliance
from storage.db import SessionLocal
from storage.models import Agent as AgentRow
from storage.models import Call

load_dotenv()

logger = logging.getLogger("acme-agent")

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
        # Full LLM output for the turn currently playing out, captured straight from the
        # token stream (Phase 6) so an interrupted turn can be compared against the
        # (possibly shorter) text the framework actually commits to history/transcript.
        # Single slot: fine because, for this POC, a new generation only starts once the
        # previous one has either finished or been interrupted.
        self._last_generated_text = ""

    async def on_enter(self) -> None:
        self.session.say(GREETING)

    async def llm_node(self, chat_ctx, tools, model_settings):
        generated = ""
        try:
            async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
                if isinstance(chunk, str):
                    generated += chunk
                elif chunk.delta and chunk.delta.content:
                    generated += chunk.delta.content
                yield chunk
        finally:
            self._last_generated_text = generated


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
        # Transcript is fully flushed by now (session has already stopped),
        # so compliance can safely read it. Caught rather than left to
        # propagate: a flaky LLM call must not block shutdown or be mistaken
        # for the call itself having failed.
        try:
            await run_compliance(call_id)
        except Exception:
            logger.exception("compliance check failed for call %s", call_id)

    ctx.add_shutdown_callback(on_shutdown)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model=model),
        tts=cartesia.TTS(voice=voice),
        # mode="vad": the default ("adaptive") calls LiveKit's cloud inference
        # service for interruption detection, which this self-hosted-only
        # project does not use (rule 2).
        # enabled/min_duration spelled out explicitly (Phase 6): they match the
        # framework defaults, stated here so the barge-in behaviour is a documented
        # decision rather than an accident of whatever the library ships next.
        turn_handling={
            "turn_detection": EnglishModel(),
            "interruption": {"mode": "vad", "enabled": True, "min_duration": 0.5},
        },
    )

    call_start_ts = time.time()
    attach_transcript_recorder(session, call_id, call_start_ts)
    attach_metrics_recorder(session, call_id)
    attach_whisper_listener(ctx.room, session, call_id)

    agent = SupportAgent(system_prompt)

    def _on_conversation_item_added(ev: ConversationItemAddedEvent) -> None:
        item = ev.item
        if not isinstance(item, ChatMessage) or item.role != "assistant" or not item.interrupted:
            return
        # Phase 6 debug dump: prove the committed history only contains what was
        # actually spoken, by printing it next to the full (longer) LLM output.
        logger.info(
            "interrupted turn — generated=%r spoken=%r",
            agent._last_generated_text,
            item.text_content,
        )
        logger.info("chat history after interruption: %s", session.history.to_dict())

    session.on("conversation_item_added", _on_conversation_item_added)

    await session.start(agent=agent, room=ctx.room)
    _mark_call_status(call_id, "active")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, agent_name=AGENT_NAME))
