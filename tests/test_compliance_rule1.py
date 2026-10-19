"""Pure, network-free unit tests for Rule 1 (AGENTS.md Phase 9 "Test it" #1).

Fake transcript lines only -- no DB, no LiveKit, no LLM.
"""

from compliance.rules import evaluate_recording_disclosure

DISCLOSURE_TEXT = "Thanks for calling Acme Telecom, this call is being recorded for quality."


def _line(text: str, ts_ms: int, speaker: str = "agent") -> dict:
    return {"speaker": speaker, "text": text, "ts_ms": ts_ms}


def test_disclosure_within_window_passes():
    result = evaluate_recording_disclosure([_line(DISCLOSURE_TEXT, 12_000)])
    assert result["passed"] is True
    assert result["evidence_line"] == DISCLOSURE_TEXT
    assert result["ts_ms"] == 12_000


def test_disclosure_after_window_fails():
    result = evaluate_recording_disclosure([_line(DISCLOSURE_TEXT, 31_000)])
    assert result["passed"] is False
    assert result["evidence_line"] is None


def test_disclosure_absent_fails():
    result = evaluate_recording_disclosure([_line("Hi, how can I help you today?", 1_000)])
    assert result["passed"] is False
    assert result["evidence_line"] is None
    assert result["ts_ms"] is None


def test_disclosure_exactly_at_window_edge_passes():
    result = evaluate_recording_disclosure([_line(DISCLOSURE_TEXT, 30_000)])
    assert result["passed"] is True
    assert result["ts_ms"] == 30_000


def test_disclosure_ignores_user_lines():
    result = evaluate_recording_disclosure(
        [_line(DISCLOSURE_TEXT, 5_000, speaker="user")]
    )
    assert result["passed"] is False
