# Voice Agent on Self-Hosted LiveKit

Operator-guided voice AI agent built on a self-hosted LiveKit server. See [AGENTS.md](AGENTS.md) for
the full phase plan this repo follows.

Status: Phase 7 (Latency measurement) in progress. Setup steps, architecture diagram, ports table,
and the final latency table will be filled in as later phases land (see Phase 10 in AGENTS.md); a
real measured report already exists at [docs/latency.md](docs/latency.md).

## Latency instrumentation (Phase 7)

Per-turn latency is read off `ChatMessage.metrics` (a dict the framework attaches to every
user/assistant turn), not hand-assembled from raw `metrics_collected` events -- the installed
livekit-agents version marks that event deprecated in favor of this. See `agent/metrics.py` for
the exact field mapping and `docs/latency.md` for a real measured report. Two approximations to
know about:

- `EOU` (end-of-turn delay) and `STT final` (transcription delay) are both measured from the same
  anchor -- the user falling silent -- and run in parallel, not sequentially, so they should not be
  summed into the total.
- The stage columns do not fully account for `Total` (`e2e_latency`): reconstructing total latency
  by adding up the stage columns undershoots the framework's own directly-measured total by roughly
  50-280ms per turn in testing, because `on_user_turn_completed_delay` and internal scheduling gaps
  between stages aren't captured as their own column. Treat `Total` as ground truth and the stage
  columns as "where the time goes," not as inputs you can re-sum to get `Total` back exactly.

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
