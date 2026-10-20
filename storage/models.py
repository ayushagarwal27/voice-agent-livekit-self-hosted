"""SQLAlchemy models. See AGENTS.md section 1 for the full target data model;
`agents` and `calls` are needed as of Phase 4."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    voice: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    room_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="created")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    compliance_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class TranscriptLine(Base):
    __tablename__ = "transcript_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String, nullable=False)  # "agent" | "user" | "operator"
    text: Mapped[str] = mapped_column(Text, nullable=False)
    ts_abs: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ts_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    interrupted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TurnMetrics(Base):
    __tablename__ = "turn_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), nullable=False)
    turn_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # All columns below are nullable: an interrupted turn can be missing its
    # later stages (e.g. cut before TTS ever started), and those are left
    # NULL rather than guessed. See agent/metrics.py for what each maps to.
    eou_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stt_final_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tts_first_audio_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_published_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Whisper(Base):
    __tablename__ = "whispers"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
