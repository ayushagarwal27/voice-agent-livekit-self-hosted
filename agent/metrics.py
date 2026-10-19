"""Per-turn latency metrics (Phase 7, AGENTS.md Part G).

AGENTS.md's plan was to subscribe to `metrics_collected` events keyed by
`speech_id`. Verified against the installed livekit-agents version (rule 7,
not assumed): `MetricsCollectedEvent` is explicitly documented there as
"Deprecated: use session_usage_updated for usage tracking. Per-turn latency
metrics are available on ChatMessage.metrics" (livekit/agents/voice/events.py).
So this reads the `MetricsReport` dict the framework already attaches to each
user/assistant `ChatMessage` (confirmed by reading `agent_activity.py`'s
`assistant_metrics`/`metrics_report` construction) instead of stitching raw
events together by hand.

Stage mapping (each field name as the framework defines it):
- eou_ms             <- user ChatMessage.metrics["end_of_turn_delay"]   user stops speaking -> turn-end decision
- stt_final_ms       <- user ChatMessage.metrics["transcription_delay"] user stops speaking -> STT final transcript
- llm_ttft_ms        <- assistant .metrics["llm_node_ttft"]             LLM generation start -> first token
- tts_first_audio_ms <- assistant .metrics["tts_node_ttfb"]             first text token sent -> first TTS audio chunk
- audio_published_ms <- assistant .metrics["playback_latency"]         first audio frame forwarded -> playback actually starts
- total_ms           <- assistant .metrics["e2e_latency"]              user stops speaking -> agent's audio actually starts playing

Approximation (also called out in the README): eou_ms and stt_final_ms are
both measured from the same anchor (the user falling silent) and can
proceed in parallel rather than strictly in sequence, so the stages do not
sum to exactly total_ms -- total_ms is measured independently by the
framework, not derived by adding the others up. scripts/latency_report.py's
sanity check accounts for this.
"""

import json
import logging

from livekit.agents import AgentSession
from livekit.agents.llm import ChatMessage, MetricsReport
from livekit.agents.voice.events import ConversationItemAddedEvent

from storage.db import SessionLocal
from storage.models import TurnMetrics

logger = logging.getLogger("acme-agent.metrics")


def _ms(seconds: float | None) -> int | None:
    if seconds is None:
        return None
    return round(seconds * 1000)


def attach_metrics_recorder(session: AgentSession, call_id: int) -> None:
    turn_no = 0
    pending_user_metrics: MetricsReport = {}

    def _on_conversation_item_added(ev: ConversationItemAddedEvent) -> None:
        nonlocal turn_no, pending_user_metrics
        item = ev.item
        if not isinstance(item, ChatMessage):
            return

        if item.role == "user":
            pending_user_metrics = item.metrics
            return

        if item.role != "assistant":
            return

        turn_no += 1
        row = {
            "call_id": call_id,
            "turn_no": turn_no,
            "eou_ms": _ms(pending_user_metrics.get("end_of_turn_delay")),
            "stt_final_ms": _ms(pending_user_metrics.get("transcription_delay")),
            "llm_ttft_ms": _ms(item.metrics.get("llm_node_ttft")),
            "tts_first_audio_ms": _ms(item.metrics.get("tts_node_ttfb")),
            "audio_published_ms": _ms(item.metrics.get("playback_latency")),
            "total_ms": _ms(item.metrics.get("e2e_latency")),
        }
        pending_user_metrics = {}
        logger.info("turn_metrics %s", json.dumps(row))

        db_session = SessionLocal()
        try:
            db_session.add(TurnMetrics(**row))
            db_session.commit()
        finally:
            db_session.close()

    session.on("conversation_item_added", _on_conversation_item_added)
