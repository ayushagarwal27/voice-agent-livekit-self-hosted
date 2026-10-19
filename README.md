# Voice Agent on Self-Hosted LiveKit

Operator-guided voice AI agent built on a self-hosted LiveKit server. See [AGENTS.md](AGENTS.md) for
the full phase plan this repo follows.

Status: Phase 2 (hard-coded voice agent) in progress. Setup steps, architecture diagram, ports table,
and latency results will be filled in as later phases land (see Phase 10 in AGENTS.md).

## Ports

| Port | Purpose | Why |
|---|---|---|
| 7880/TCP | HTTP API and WebSocket signalling | All client/server control traffic (room join, track negotiation) goes over this port. |
| 7881/TCP | ICE/TCP fallback | Used when UDP is blocked by a restrictive network; media falls back to TCP at the cost of higher latency. |
| 50000-50100/UDP | Media (RTP/SRTP) | Actual audio/video packets. One port is used per connection; kept small (100 ports) since Docker Desktop maps each one individually and mapping thousands is slow. |
| 3478/5349 (TURN) | Not enabled | Only needed when both peers are behind restrictive NATs/firewalls that block direct UDP/TCP to the server. Not required for this local/self-hosted proof of concept; would add cost (relayed bandwidth) and complexity (TLS cert for TURNS) with no benefit on a local network. |

## Quickstart (placeholder, expanded in Phase 10)

```bash
cp .env.example .env            # fill in your own secrets/keys
uv sync                         # install Python deps
docker compose up -d livekit    # start the self-hosted LiveKit server
uv run python scripts/smoke_join.py   # Phase 1 smoke test
```
