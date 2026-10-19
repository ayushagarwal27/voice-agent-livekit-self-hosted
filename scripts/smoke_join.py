"""Mint a LiveKit access token and join a room, to smoke-test the self-hosted server.

Usage: uv run python scripts/smoke_join.py [room_name]
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from livekit import api, rtc

load_dotenv()

LIVEKIT_URL = os.environ["LIVEKIT_URL"]
LIVEKIT_API_KEY = os.environ["LIVEKIT_API_KEY"]
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]


def make_token(room_name: str, identity: str) -> str:
    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
    )
    return token.to_jwt()


async def main(room_name: str) -> None:
    jwt = make_token(room_name, "smoke-test")
    print(f"Minted token for room '{room_name}'")

    room = rtc.Room()

    @room.on("participant_connected")
    def _on_participant_connected(participant: rtc.RemoteParticipant) -> None:
        print(f"participant_connected: {participant.identity}")

    await room.connect(LIVEKIT_URL, jwt)
    print(f"Connected to {LIVEKIT_URL} as 'smoke-test' in room '{room_name}'")
    print(f"Local participants seen by server: {list(room.remote_participants.keys())}")

    await asyncio.sleep(2)
    await room.disconnect()
    print("Disconnected cleanly.")


if __name__ == "__main__":
    room_name = sys.argv[1] if len(sys.argv) > 1 else "smoke-test-room"
    asyncio.run(main(room_name))
