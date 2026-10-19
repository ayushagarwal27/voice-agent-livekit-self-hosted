"""Create the default Acme Telecom support persona in the DB (Phase 3).

Usage: uv run python -m scripts.seed_agent
(run as a module, not a bare script path, so the `storage` package resolves)
"""

# Cartesia's default voice id (Phase 4 wires `agents.voice` through to
# `cartesia.TTS(voice=...)`, unlike Phase 3 where it was unused).
DEFAULT_VOICE = "f786b574-daa5-4673-aa0c-cbe3e8534c02"

from storage.db import SessionLocal, init_db
from storage.models import Agent

PERSONA = (
    "You are a customer support voice agent for Acme Telecom, a fictional phone and "
    "internet provider. Be friendly, concise, and to the point. Speak in short, plain "
    "sentences meant to be heard, not read: no markdown, no bullet lists, no headings. "
    "If you don't know something, say so plainly instead of making it up."
)


def main() -> None:
    init_db()
    session = SessionLocal()
    try:
        existing = session.query(Agent).filter_by(name="Acme Support").first()
        if existing is not None:
            print(f"Already seeded: agent id={existing.id}")
            return

        agent = Agent(
            name="Acme Support",
            system_prompt=PERSONA,
            voice=DEFAULT_VOICE,
            model="gpt-4.1",
        )
        session.add(agent)
        session.commit()
        session.refresh(agent)
        print(f"Seeded agent id={agent.id}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
