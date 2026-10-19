"""Run both Phase 9 compliance rules for a call and persist the result to
`calls.compliance_json`. Idempotent: calling it again just re-evaluates the
same (immutable, post-call) transcript and overwrites the stored result --
safe to re-run by hand via `scripts/run_compliance.py`.

Called from the worker's shutdown callback (`agent/worker.py`), after the
transcript has been flushed to `transcript_lines`.
"""

import json

from compliance.llm_check import evaluate_no_refund_promise
from compliance.rules import evaluate_recording_disclosure
from storage.db import SessionLocal
from storage.models import Call, TranscriptLine


def _load_lines(call_id: int) -> list[dict]:
    db_session = SessionLocal()
    try:
        rows = (
            db_session.query(TranscriptLine)
            .filter_by(call_id=call_id)
            .order_by(TranscriptLine.seq)
            .all()
        )
        return [{"speaker": row.speaker, "text": row.text, "ts_ms": row.ts_ms} for row in rows]
    finally:
        db_session.close()


async def run_compliance(call_id: int) -> dict:
    lines = _load_lines(call_id)

    result = {
        "recording_disclosure": evaluate_recording_disclosure(lines),
        "no_refund_promise": await evaluate_no_refund_promise(lines),
    }

    db_session = SessionLocal()
    try:
        call = db_session.get(Call, call_id)
        if call is not None:
            call.compliance_json = json.dumps(result)
            db_session.commit()
    finally:
        db_session.close()

    return result
