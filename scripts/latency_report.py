"""Print a markdown latency report from `turn_metrics` (Phase 7).

Usage: uv run python -m scripts.latency_report [call_id ...]
With no arguments, reports over every turn in the DB; pass one or more
call ids to restrict the report to those calls.
"""

import statistics
import sys

from sqlalchemy import select

from storage.db import SessionLocal
from storage.models import TurnMetrics

STAGE_COLUMNS = [
    ("eou_ms", "EOU"),
    ("stt_final_ms", "STT final"),
    ("llm_ttft_ms", "LLM TTFT"),
    ("tts_first_audio_ms", "TTS first audio"),
    ("audio_published_ms", "Audio published"),
    ("total_ms", "Total"),
]


def _fmt(value: int | None) -> str:
    return "-" if value is None else str(value)


def _percentile(values: list[int], pct: float) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1]


def _print_per_turn_table(rows: list[TurnMetrics]) -> None:
    headers = ["call_id", "turn_no"] + [label for _, label in STAGE_COLUMNS]
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        cells = [str(row.call_id), str(row.turn_no)] + [
            _fmt(getattr(row, col)) for col, _ in STAGE_COLUMNS
        ]
        print("| " + " | ".join(cells) + " |")


def _print_summary_table(rows: list[TurnMetrics]) -> None:
    print("\n| Stage | n | avg | p50 | p95 |")
    print("|---|---|---|---|---|")
    for col, label in STAGE_COLUMNS:
        values = [v for v in (getattr(row, col) for row in rows) if v is not None]
        if not values:
            print(f"| {label} | 0 | - | - | - |")
            continue
        avg = round(statistics.mean(values))
        p50 = round(_percentile(values, 50)) if len(values) > 1 else values[0]
        p95 = round(_percentile(values, 95)) if len(values) > 1 else values[0]
        print(f"| {label} | {len(values)} | {avg} | {p50} | {p95} |")


def _print_sanity_check(rows: list[TurnMetrics]) -> None:
    # eou_ms and stt_final_ms are measured from the same anchor (user falls
    # silent) and can run in parallel, so only the larger of the two is
    # on the critical path to the LLM call starting; approx_total is a
    # reconstruction of total_ms from the individual stages, to check they
    # roughly agree (see agent/metrics.py for the full approximation note).
    print("\n### Sanity check: stages vs. measured total\n")
    print("| call_id | turn_no | approx_total_ms | total_ms | delta_ms |")
    print("|---|---|---|---|---|")
    for row in rows:
        if row.total_ms is None:
            continue
        gating = max(row.eou_ms or 0, row.stt_final_ms or 0)
        approx_total = gating + (row.llm_ttft_ms or 0) + (row.tts_first_audio_ms or 0) + (
            row.audio_published_ms or 0
        )
        delta = approx_total - row.total_ms
        print(f"| {row.call_id} | {row.turn_no} | {approx_total} | {row.total_ms} | {delta:+d} |")


def main() -> None:
    call_ids = [int(arg) for arg in sys.argv[1:]]

    db_session = SessionLocal()
    try:
        stmt = select(TurnMetrics).order_by(TurnMetrics.call_id, TurnMetrics.turn_no)
        if call_ids:
            stmt = stmt.where(TurnMetrics.call_id.in_(call_ids))
        rows = list(db_session.scalars(stmt))
    finally:
        db_session.close()

    if not rows:
        print("No turn_metrics rows found.")
        return

    print(f"## Latency report ({len(rows)} turns, {len({r.call_id for r in rows})} calls)\n")
    _print_per_turn_table(rows)
    _print_summary_table(rows)
    _print_sanity_check(rows)


if __name__ == "__main__":
    main()
