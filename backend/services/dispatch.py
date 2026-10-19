"""Create the LiveKit room and the explicit agent dispatch for a call.

Explicit dispatch (AGENTS.md section 1): the worker registers with
`agent_name="support-agent"` and does not auto-join every room. The backend
creates the room, then asks the server to dispatch that named agent into it,
passing `{call_id, agent_id}` as job metadata so the worker knows which
persona and call row to load.
"""

from livekit import api

AGENT_NAME = "support-agent"


async def create_room_and_dispatch(room_name: str, metadata: str) -> None:
    async with api.LiveKitAPI() as lk:
        await lk.room.create_room(api.CreateRoomRequest(name=room_name))
        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=metadata,
            )
        )
