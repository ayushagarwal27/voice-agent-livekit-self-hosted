"""Voice agent for Acme Telecom customer support (Phase 2: hard-coded config).

The persona below is a temporary constant per AGENTS.md rule 5. Phase 4 moves
it into the `agents` table and removes this constant.

Usage:
  uv run -m livekit.agents download-files   # once, to fetch the VAD/turn-detector models
  uv run python agent/worker.py console      # talk to it from the terminal (mic/speakers)
  uv run python agent/worker.py dev          # join real rooms on the self-hosted LiveKit server
"""

from dotenv import load_dotenv
from livekit.agents import Agent, AgentSession, JobContext, JobProcess, WorkerOptions, cli
from livekit.plugins import cartesia, deepgram, openai, silero
from livekit.plugins.turn_detector.english import EnglishModel

load_dotenv()

PERSONA = (
    "You are a customer support voice agent for Acme Telecom, a fictional phone and "
    "internet provider. Be friendly, concise, and to the point. Speak in short, plain "
    "sentences meant to be heard, not read: no markdown, no bullet lists, no headings. "
    "If you don't know something, say so plainly instead of making it up."
)

GREETING = (
    "Thanks for calling Acme Telecom, this call is being recorded for quality and "
    "training. How can I help you today?"
)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


class SupportAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=PERSONA)

    async def on_enter(self) -> None:
        self.session.say(GREETING)


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(),
        tts=cartesia.TTS(),
        # mode="vad": the default ("adaptive") calls LiveKit's cloud inference
        # service for interruption detection, which this self-hosted-only
        # project does not use (rule 2).
        turn_handling={"turn_detection": EnglishModel(), "interruption": {"mode": "vad"}},
    )

    await session.start(agent=SupportAgent(), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
