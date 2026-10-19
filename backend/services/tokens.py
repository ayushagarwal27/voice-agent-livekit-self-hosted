"""Mint LiveKit access tokens (AGENTS.md section 1: customer vs operator grants)."""

from datetime import timedelta

from livekit import api

CUSTOMER_TOKEN_TTL = timedelta(minutes=15)


def mint_customer_token(room_name: str, identity: str) -> str:
    token = (
        api.AccessToken()
        .with_identity(identity)
        .with_name(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_ttl(CUSTOMER_TOKEN_TTL)
    )
    return token.to_jwt()
