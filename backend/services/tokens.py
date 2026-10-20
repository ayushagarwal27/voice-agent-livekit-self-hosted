"""Mint LiveKit access tokens (AGENTS.md section 1: customer vs operator grants)."""

from datetime import timedelta

from livekit import api

CUSTOMER_TOKEN_TTL = timedelta(minutes=15)
OPERATOR_TOKEN_TTL = timedelta(minutes=15)
TAKEOVER_TOKEN_TTL = timedelta(minutes=15)


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


def mint_operator_token(room_name: str, identity: str) -> str:
    """Hidden, listen-only grant (AGENTS.md section 1): the operator hears
    everyone and can send whisper data, but never publishes media and is
    never shown as a participant to the customer or the agent."""
    token = (
        api.AccessToken()
        .with_identity(identity)
        .with_name(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                hidden=True,
                can_publish=False,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_ttl(OPERATOR_TOKEN_TTL)
    )
    return token.to_jwt()


def mint_operator_takeover_token(room_name: str, identity: str) -> str:
    """Visible, mic-publishing grant (Stretch S1): minted when the operator clicks
    "Take over." LiveKit has no partial-visibility mode, so publishing a mic track
    means giving up `hidden` -- a documented trade-off, not an oversight (see
    README known limitations). Still can't subscribe to nothing new; kept
    `can_subscribe=True` so the operator keeps hearing both sides mid-takeover."""
    token = (
        api.AccessToken()
        .with_identity(identity)
        .with_name(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                hidden=False,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_ttl(TAKEOVER_TOKEN_TTL)
    )
    return token.to_jwt()
