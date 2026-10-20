"""Operator take-over channel (Stretch S1).

The operator can publish a real mic track into the room and talk to the
customer directly. Two data messages (both addressed only to the agent's
identity, same pattern as `agent/whisper.py`) bracket the hand-off:

- `operator_takeover_start`: sent once the operator's mic track is live.
  The agent mutes its own TTS output and stops generating new replies
  (`session.output`/`session.input` audio toggles -- public AgentSession
  API, not private scheduling internals), then starts transcribing the
  operator's track with its own throwaway Deepgram STT stream so nothing
  the human says is lost.
- `operator_takeover_end`: sent when the operator clicks "Hand back". The
  agent stops that STT stream, folds whatever the human said into its chat
  context as a private note (so the next reply is aware of it, the same
  "append, don't force a reply" trick as whispers), and un-mutes itself.

Trade-off (documented, not accidental): while muted, the agent also stops
listening to the *customer* -- `session.input.set_audio_enabled(False)`
pauses the whole STT/turn-detection pipeline, not just the reply step, so
the customer talking over the human operator is not transcribed or acted
on. Pausing input was the simplest way to guarantee no reply gets generated
mid-takeover without reaching into AgentActivity's private scheduling
state; for this proof of concept the customer is expected to listen while
the human has the floor, same as any real call transfer.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from livekit import rtc
from livekit.agents import AgentSession
from livekit.agents.stt import SpeechEventType
from livekit.plugins import deepgram

from agent.transcript import next_seq
from storage.db import SessionLocal
from storage.models import TranscriptLine

logger = logging.getLogger("acme-agent")

TAKEOVER_START_TOPIC = "operator_takeover_start"
TAKEOVER_END_TOPIC = "operator_takeover_end"

_HANDBACK_PREFACE = (
    "Private note, not something the caller said: a human operator just took over this "
    "call directly (the caller heard the operator, not you) and said the following, then "
    "handed the call back to you. Continue the conversation naturally, taking it into "
    "account. Never mention the hand-off, the operator, or this note to the caller."
)


def _persist_operator_line(call_id: int, text: str, call_start_ts: float) -> None:
    db_session = SessionLocal()
    try:
        now = time.time()
        db_session.add(
            TranscriptLine(
                call_id=call_id,
                seq=next_seq(db_session, call_id),
                speaker="operator",
                text=text,
                ts_abs=datetime.now(timezone.utc),
                ts_ms=max(0, round((now - call_start_ts) * 1000)),
                interrupted=False,
            )
        )
        db_session.commit()
    finally:
        db_session.close()


class _TakeoverState:
    def __init__(self) -> None:
        self.active = False
        self.operator_identity: str | None = None
        self.stt_stream = None
        self.lines: list[str] = []
        self.tasks: list[asyncio.Task] = []


def attach_takeover_listener(
    room: rtc.Room, session: AgentSession, call_id: int, call_start_ts: float
) -> None:
    state = _TakeoverState()

    def _attach_stt_if_ready(participant: rtc.RemoteParticipant) -> None:
        if not state.active or participant.identity != state.operator_identity:
            return
        if state.stt_stream is not None:
            return  # already attached for this takeover
        for pub in participant.track_publications.values():
            if pub.kind == rtc.TrackKind.KIND_AUDIO and pub.track is not None:
                _start_transcribing(pub.track)
                return

    def _start_transcribing(track: rtc.Track) -> None:
        stt_stream = deepgram.STT().stream()
        state.stt_stream = stt_stream
        audio_stream = rtc.AudioStream(track)

        async def _pump_audio() -> None:
            try:
                async for ev in audio_stream:
                    stt_stream.push_frame(ev.frame)
            except Exception:
                logger.exception("takeover audio pump failed for call %s", call_id)

        async def _collect_transcripts() -> None:
            try:
                async for ev in stt_stream:
                    if ev.type == SpeechEventType.FINAL_TRANSCRIPT:
                        text = ev.alternatives[0].text.strip()
                        if not text:
                            continue
                        state.lines.append(text)
                        _persist_operator_line(call_id, text, call_start_ts)
            except Exception:
                logger.exception("takeover transcript collection failed for call %s", call_id)

        state.tasks = [
            asyncio.create_task(_pump_audio()),
            asyncio.create_task(_collect_transcripts()),
        ]

    async def _stop_transcribing() -> None:
        for task in state.tasks:
            task.cancel()
        for task in state.tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        if state.stt_stream is not None:
            await state.stt_stream.aclose()
        state.tasks = []
        state.stt_stream = None

    async def _start_takeover(operator_identity: str) -> None:
        logger.info("takeover started for call %s by %s", call_id, operator_identity)
        if state.active:
            # A second "start" arrived without an "end" in between -- a reload of the
            # operator tab, or a second tab, re-sending it. Close out the previous STT
            # stream cleanly instead of overwriting it out from under its own tasks, but
            # keep `state.lines` (not reset below) so words from the first session aren't
            # lost from the eventual hand-back note.
            await _stop_transcribing()
        else:
            state.lines = []
        state.active = True
        state.operator_identity = operator_identity

        session.interrupt()
        session.output.set_audio_enabled(False)
        session.input.set_audio_enabled(False)

        participant = room.remote_participants.get(operator_identity)
        if participant is not None:
            _attach_stt_if_ready(participant)

    async def _end_takeover() -> None:
        logger.info("takeover ended for call %s", call_id)
        await _stop_transcribing()

        if state.lines:
            said = " ".join(state.lines)
            agent = session.current_agent
            chat_ctx = agent.chat_ctx.copy()
            chat_ctx.add_message(role="system", content=f"{_HANDBACK_PREFACE}\nOperator said: {said}")
            await agent.update_chat_ctx(chat_ctx)

        state.active = False
        state.operator_identity = None
        session.input.set_audio_enabled(True)
        session.output.set_audio_enabled(True)

    def _on_data_received(packet: rtc.DataPacket) -> None:
        if packet.topic == TAKEOVER_START_TOPIC:
            identity = packet.participant.identity if packet.participant else None
            if identity:
                asyncio.create_task(_start_takeover(identity))
        elif packet.topic == TAKEOVER_END_TOPIC:
            asyncio.create_task(_end_takeover())

    def _on_track_subscribed(
        track: rtc.Track, _pub: rtc.TrackPublication, participant: rtc.RemoteParticipant
    ) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            _attach_stt_if_ready(participant)

    room.on("data_received", _on_data_received)
    room.on("track_subscribed", _on_track_subscribed)
