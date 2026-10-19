# Latency report (Phase 7)

Generated with `uv run python -m scripts.latency_report`, from 3 real calls (ids 18-20)
against the self-hosted LiveKit server, Deepgram STT, OpenAI `gpt-4.1`, and Cartesia TTS.
6 questions per call, played as synthesized audio (not a human mic) so the test is
repeatable; turn 1 of each call is the scripted greeting (`session.say`), which never
goes through the LLM and so is missing EOU/STT/LLM/total figures — that's expected, not
a gap in the instrumentation.

## Latency report (21 turns, 3 calls)

| call_id | turn_no | EOU | STT final | LLM TTFT | TTS first audio | Audio published | Total |
|---|---|---|---|---|---|---|---|
| 18 | 1 | - | - | - | 165 | 158 | - |
| 18 | 2 | 584 | 521 | 688 | 147 | 0 | 1445 |
| 18 | 3 | 595 | 474 | 853 | 181 | 0 | 1711 |
| 18 | 4 | 598 | 508 | 735 | 159 | 0 | 1474 |
| 18 | 5 | 597 | 491 | 1016 | 160 | 0 | 1853 |
| 18 | 6 | 590 | 461 | 751 | 192 | 0 | 1585 |
| 18 | 7 | 591 | 513 | 1012 | 181 | 0 | 2062 |
| 19 | 1 | - | - | - | 162 | 0 | - |
| 19 | 2 | 581 | 452 | 969 | 160 | 0 | 1763 |
| 19 | 3 | 594 | 520 | 823 | 147 | 1 | 1725 |
| 19 | 4 | 593 | 470 | 917 | 167 | 0 | 1750 |
| 19 | 5 | 584 | 472 | 829 | 178 | 3 | 1736 |
| 19 | 6 | 601 | 460 | 957 | 168 | 0 | 1881 |
| 19 | 7 | 590 | 482 | 799 | 166 | 0 | 1762 |
| 20 | 1 | - | - | - | 159 | 0 | - |
| 20 | 2 | 581 | 474 | 879 | 146 | 0 | 1538 |
| 20 | 3 | 587 | 533 | 923 | 180 | 0 | 1895 |
| 20 | 4 | 599 | 466 | 921 | 179 | 1 | 1784 |
| 20 | 5 | 587 | 464 | 935 | 160 | 1 | 1830 |
| 20 | 6 | 587 | 432 | 859 | 151 | 0 | 1665 |
| 20 | 7 | 600 | 512 | 851 | 169 | 0 | 1843 |

All times in ms.

### Summary (avg / p50 / p95)

| Stage | n | avg | p50 | p95 |
|---|---|---|---|---|
| EOU (user stops speaking -> turn-end decision) | 18 | 591 | 590 | 600 |
| STT final (user stops speaking -> final transcript) | 18 | 484 | 474 | 523 |
| LLM TTFT (generation start -> first token) | 18 | 873 | 869 | 1013 |
| TTS first audio (first text token -> first audio chunk) | 21 | 166 | 165 | 181 |
| Audio published (first frame forwarded -> playback starts) | 21 | 8 | 0 | 3 |
| Total (user stops speaking -> agent's audio actually starts) | 18 | 1739 | 1756 | 1920 |

### Sanity check: stages vs. measured total

`approx_total_ms = max(EOU, STT final) + LLM TTFT + TTS first audio + Audio published`,
compared against the independently-measured `Total` (the framework's own `e2e_latency`).
They land in the same ballpark (within roughly 5-15%) but `approx_total` consistently
undershoots `Total` by 50-280ms — see "Approximations" below for why.

| call_id | turn_no | approx_total_ms | total_ms | delta_ms |
|---|---|---|---|---|
| 18 | 2 | 1419 | 1445 | -26 |
| 18 | 3 | 1629 | 1711 | -82 |
| 18 | 4 | 1492 | 1474 | +18 |
| 18 | 5 | 1773 | 1853 | -80 |
| 18 | 6 | 1533 | 1585 | -52 |
| 18 | 7 | 1784 | 2062 | -278 |
| 19 | 2 | 1710 | 1763 | -53 |
| 19 | 3 | 1565 | 1725 | -160 |
| 19 | 4 | 1677 | 1750 | -73 |
| 19 | 5 | 1594 | 1736 | -142 |
| 19 | 6 | 1726 | 1881 | -155 |
| 19 | 7 | 1555 | 1762 | -207 |
| 20 | 2 | 1606 | 1538 | +68 |
| 20 | 3 | 1690 | 1895 | -205 |
| 20 | 4 | 1700 | 1784 | -84 |
| 20 | 5 | 1683 | 1830 | -147 |
| 20 | 6 | 1597 | 1665 | -68 |
| 20 | 7 | 1620 | 1843 | -223 |

## Which stage to attack first

**LLM TTFT** (avg 873ms, p95 1013ms) is the single largest sequential stage, and the
clearest target: it alone is bigger than EOU and roughly double STT final, and unlike
EOU/STT (which overlap with each other, not with the LLM call) it sits squarely on the
critical path between "turn ends" and "audio starts." The fastest wins, in order, would
be: (1) switch to a smaller/faster model or a provider with lower TTFT for this
persona's fairly short, templated replies, (2) use OpenAI prompt caching on the system
prompt (static across every turn) to cut prefill time, and (3) consider streaming the
very first sentence to TTS more aggressively (`llm_node_ttfs` here trails `llm_node_ttft`
by only ~10-200ms, so there isn't much slack being lost at the hand-off itself — the win
is in the LLM call, not the LLM->TTS seam). EOU (~590ms) is mostly VAD/turn-detector
endpointing delay and is not worth touching yet; it's already in the normal range for a
local turn-detector model and shaving it further risks false endpointing.

## Approximations (see agent/metrics.py for the full note)

- **EOU and STT final are not sequential.** Both are measured from the same anchor (the
  moment the user stops speaking) and the framework runs them in parallel rather than
  one blocking the other, so summing them double-counts time that was never actually a
  sequential wait. The sanity-check table above uses `max(EOU, STT final)` for this
  reason.
- **`approx_total` undershoots `Total` by 50-280ms.** `Total` (`e2e_latency`) is measured
  directly by the framework as `assistant_started_speaking_at - user_stopped_speaking_at`.
  `approx_total` is reconstructed by this report from the individual stage fields, which
  do not include `on_user_turn_completed_delay` (time to run the app's
  `on_user_turn_completed` hook -- near-zero here since this agent doesn't override it,
  but still real) or the scheduler/queueing gaps between stages that the framework does
  not expose as a named field. `Total` is the trustworthy number; the per-stage columns
  are for seeing *where* the time goes, not for re-deriving `Total` exactly.
- **`Audio published` (`playback_latency`) is near-zero by construction here.** It is
  "time between forwarding the first audio frame to the local room output and that
  output reporting playback started," which is sub-millisecond for the default in-process
  room output used in this project. It would become meaningful with a remote avatar
  worker in the chain, which this project does not use.
- **Turn 1 of every call (the greeting) has no EOU/STT/LLM/Total figures.** It is spoken
  via `session.say()` directly, not generated through `llm_node`, so there is no user
  turn and no LLM call to measure.
