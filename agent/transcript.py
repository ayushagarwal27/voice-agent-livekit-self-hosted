"""Persist the session's chat history to `transcript_lines` (Phase 5).

The transcript is the source of truth and is built from `AgentSession`
events, not reconstructed from the browser (AGENTS.md section 1). Agent
`ChatMessage`s are stamped by the framework with `created_at` set to the
time the agent *started speaking* that line (verified by reading
`livekit.agents.voice.agent_activity`), which is exactly what AGENTS.md
asks for, so no extra bookkeeping is needed to get that right.
"""

from datetime import datetime, timezone

from livekit.agents import AgentSession
from livekit.agents.llm import ChatMessage
from livekit.agents.voice.events import ConversationItemAddedEvent

from storage.db import SessionLocal
from storage.models import TranscriptLine

_SPEAKER_BY_ROLE = {"assistant": "agent", "user": "user"}


def attach_transcript_recorder(session: AgentSession, call_id: int, call_start_ts: float) -> None:
    seq = 0

    def _on_conversation_item_added(ev: ConversationItemAddedEvent) -> None:
        nonlocal seq
        item = ev.item
        if not isinstance(item, ChatMessage):
            return
        speaker = _SPEAKER_BY_ROLE.get(item.role)
        if speaker is None:
            return
        text = item.text_content
        if not text:
            return

        seq += 1
        ts_ms = max(0, round((item.created_at - call_start_ts) * 1000))

        db_session = SessionLocal()
        try:
            db_session.add(
                TranscriptLine(
                    call_id=call_id,
                    seq=seq,
                    speaker=speaker,
                    text=text,
                    ts_abs=datetime.fromtimestamp(item.created_at, tz=timezone.utc),
                    ts_ms=ts_ms,
                    interrupted=item.interrupted,
                )
            )
            db_session.commit()
        finally:
            db_session.close()

    session.on("conversation_item_added", _on_conversation_item_added)
