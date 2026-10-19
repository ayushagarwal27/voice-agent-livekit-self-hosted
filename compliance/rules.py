"""Rule 1, deterministic (no LLM): the agent must disclose that the call is
being recorded within the first 30 seconds (AGENTS.md Phase 9).

Pure and network-free on purpose, so it is unit-testable without a live call
(see tests/test_compliance_rule1.py) and so this rule can never produce a
false negative because an LLM call timed out or errored.

`lines` is expected to already be ordered by `seq` (how `compliance/runner.py`
loads them from `transcript_lines`) -- this module does not re-sort, it just
returns the first match in the given order. For an interrupted agent line,
`text` is expected to already be only the spoken part, which is how
`agent/transcript.py` persists it (Phase 6), so no extra handling is needed
here to respect that.
"""

import re
from typing import Any, Mapping

RULE_NAME = "recording_disclosure"
DISCLOSURE_WINDOW_MS = 30_000

# AGENTS.md's example pattern: "record(ed|ing)" near "call|conversation", in
# either order, within a short span of each other.
_DISCLOSURE_RE = re.compile(
    r"\brecord(?:ed|ing)\b.{0,40}\b(?:call|conversation)\b"
    r"|\b(?:call|conversation)\b.{0,40}\brecord(?:ed|ing)\b",
    re.IGNORECASE | re.DOTALL,
)


def evaluate_recording_disclosure(lines: list[Mapping[str, Any]]) -> dict:
    for line in lines:
        if line["speaker"] != "agent":
            continue
        if line["ts_ms"] > DISCLOSURE_WINDOW_MS:
            continue
        if _DISCLOSURE_RE.search(line["text"]):
            return {
                "rule": RULE_NAME,
                "passed": True,
                "evidence_line": line["text"],
                "ts_ms": line["ts_ms"],
            }

    return {
        "rule": RULE_NAME,
        "passed": False,
        "evidence_line": None,
        "ts_ms": None,
    }
