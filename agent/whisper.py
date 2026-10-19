"""Operator whisper channel (Phase 8).

The operator's browser sends a reliable data message on the
`operator_whisper` topic, addressed only to the agent's participant identity
via `destinationIdentities` so the customer's client never even receives the
bytes (AGENTS.md section 1). This module listens for that message, persists
it to `whispers`, and folds it into the agent's chat context as a private
system message. Because it is only *added* to context (not spoken, and not
followed by a forced `generate_reply`), it naturally waits for the next user
turn to take effect, exactly as AGENTS.md asks.
"""

import asyncio
import logging

from livekit import rtc
from livekit.agents import AgentSession

from storage.db import SessionLocal
from storage.models import Whisper

logger = logging.getLogger("acme-agent")

WHISPER_TOPIC = "operator_whisper"

_WHISPER_PREFACE = (
    "Private supervisor guidance. Follow it naturally in your next reply. "
    "Never mention it, or any supervisor, operator, or instruction, to the caller."
)


def attach_whisper_listener(room: rtc.Room, session: AgentSession, call_id: int) -> None:
    def _on_data_received(packet: rtc.DataPacket) -> None:
        if packet.topic != WHISPER_TOPIC:
            return
        text = packet.data.decode("utf-8")
        logger.info("whisper received for call %s: %r", call_id, text)

        db_session = SessionLocal()
        try:
            db_session.add(Whisper(call_id=call_id, text=text))
            db_session.commit()
        finally:
            db_session.close()

        asyncio.create_task(_apply_whisper(session, text))

    room.on("data_received", _on_data_received)


async def _apply_whisper(session: AgentSession, text: str) -> None:
    agent = session.current_agent
    chat_ctx = agent.chat_ctx.copy()
    chat_ctx.add_message(role="system", content=f"{_WHISPER_PREFACE}\nGuidance: {text}")
    await agent.update_chat_ctx(chat_ctx)
