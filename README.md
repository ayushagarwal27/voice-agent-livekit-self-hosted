# Voice Agent on Self-Hosted LiveKit

Operator-guided voice AI agent built on a self-hosted LiveKit server. See [AGENTS.md](AGENTS.md) for
the full phase plan this repo follows.

Status: Phase 8 (Operator: listen + whisper) in progress. Setup steps, architecture diagram, ports
table, and the final latency table will be filled in as later phases land (see Phase 10 in
AGENTS.md); a real measured latency report already exists at `docs/latency.md` (kept out of git for
now, see `.gitignore`).

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

## Operator: listen + whisper (Phase 8)

A hidden operator can join any call, hear both sides, and steer the agent without the customer
ever knowing. `POST /calls/{id}/operator-token` mints a token with `hidden=True`,
`can_publish=False`, `can_subscribe=True`, `can_publish_data=True` (`backend/services/tokens.py`):
LiveKit itself never tells the customer's client that this participant exists, which is what
guarantees invisibility -- it isn't just the browser UI choosing not to show it.

`web/operator.html` + `operator.js` join the room, play both remote audio tracks, show the same
`lk.transcription` live transcript the customer sees, and send guidance with
`localParticipant.publishData(bytes, {reliable: true, destinationIdentities: [agentIdentity], topic:
"operator_whisper"})`. `destinationIdentities` means the bytes are routed only to the agent's
participant -- the customer's client never receives them on the wire, regardless of what its JS does.

`agent/whisper.py` listens for `data_received` on that topic, persists the text to `whispers`, and
adds it to the agent's chat context as a private system message ("Private supervisor guidance...
Never mention it..."). Because this only appends to context rather than forcing an immediate reply,
it naturally waits for the next user turn, as AGENTS.md asks.

Two things worth knowing:

- **The guidance isn't consumed after one reply.** It stays in context for every subsequent LLM
  call in the session, not just the next one. For this proof of concept that's an acceptable
  simplification (whispers in testing were one-shot asks like "offer a discount"), but a longer
  call with several different whispers would need the oldest ones pruned or superseded explicitly.
- **Whispers are an explicit prompt-injection surface.** They are injected into the LLM's context
  with no validation of their content, by design (that's the point of a whisper), so anything with
  access to a valid operator token can make the agent say or do anything a sufficiently convincing
  system message can induce. This is acceptable for a trusted internal operator in this proof of
  concept, but would need an allow-list or stricter framing before letting less-trusted operators near it.

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
