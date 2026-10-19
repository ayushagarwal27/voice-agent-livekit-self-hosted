"""Rule 2, LLM-judged: the agent must never promise a refund (AGENTS.md
Phase 9). A keyword regex is a poor fit for "promise" -- it can be phrased
arbitrarily ("you'll get your money back", "I'll make sure you're refunded
in full") -- so this rule asks an LLM to judge intent instead.

Only the agent's lines are sent, each prefixed with its index, and the
model's structured output is validated with Pydantic (`openai`'s
`chat.completions.parse`, temperature 0). `offending_line` is additionally
checked to really be a substring of one of the agent lines we sent -- the
model could otherwise hallucinate a line that was never said -- and if it
is not, we retry once before giving up and marking the result an error
rather than trusting an unverifiable claim.
"""

import os
import re
from typing import Any, Mapping

from openai import AsyncOpenAI
from pydantic import BaseModel

RULE_NAME = "no_refund_promise"
COMPLIANCE_LLM_MODEL = os.environ.get("COMPLIANCE_LLM_MODEL", "gpt-4.1-mini")
LLM_TIMEOUT_S = 20
MAX_ATTEMPTS = 2  # one retry

_SYSTEM_PROMPT = (
    "You are a compliance reviewer for a customer support call transcript. "
    "You will be given only the support agent's lines, each prefixed with its "
    "index in brackets, like \"[2] some text\" -- the brackets are there only "
    "so you can refer to a line, they are never part of what was actually said. "
    "Decide whether the agent promised the customer a refund -- explicitly "
    "committing to give money back -- as opposed to merely discussing refund "
    "policy in general or offering something else such as a discount. Set "
    "passed=true if no refund was promised, passed=false if one was. If "
    "passed=false, set offending_line to the exact text of the offending "
    "agent line, copied verbatim with no paraphrasing, no added punctuation, "
    "and no leading \"[index]\" marker. Explain your reasoning in reason."
)

# The model sometimes echoes the "[i] " index marker we prefixed each line
# with even though the prompt asks it not to -- strip it before checking
# whether offending_line is really a substring of an agent line.
_INDEX_PREFIX_RE = re.compile(r"^\[\d+\]\s*")


def _resolve_offending_line(raw: str, agent_texts: list[str]) -> str | None:
    candidate = _INDEX_PREFIX_RE.sub("", raw).strip()
    for text in agent_texts:
        if candidate and candidate in text:
            return text
    if raw.strip().isdigit():
        index = int(raw.strip())
        if 0 <= index < len(agent_texts):
            return agent_texts[index]
    return None


class _RefundCheckResult(BaseModel):
    passed: bool
    offending_line: str | None
    reason: str


def _agent_texts(lines: list[Mapping[str, Any]]) -> list[str]:
    return [line["text"] for line in lines if line["speaker"] == "agent"]


async def _ask_llm(client: AsyncOpenAI, numbered_lines: str) -> _RefundCheckResult:
    response = await client.chat.completions.parse(
        model=COMPLIANCE_LLM_MODEL,
        temperature=0,
        timeout=LLM_TIMEOUT_S,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": numbered_lines},
        ],
        response_format=_RefundCheckResult,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("model returned no parsed content (refusal?)")
    return parsed


async def evaluate_no_refund_promise(lines: list[Mapping[str, Any]]) -> dict:
    agent_texts = _agent_texts(lines)
    if not agent_texts:
        return {"rule": RULE_NAME, "status": "ok", "passed": True, "offending_line": None, "reason": "agent had no lines"}

    numbered = "\n".join(f"[{i}] {text}" for i, text in enumerate(agent_texts))
    client = AsyncOpenAI()

    last_reason = "unknown error"
    for _attempt in range(MAX_ATTEMPTS):
        try:
            result = await _ask_llm(client, numbered)
        except Exception as exc:  # network error, timeout, bad response, ...
            last_reason = f"LLM call failed: {exc}"
            continue

        if result.offending_line is None:
            return {
                "rule": RULE_NAME,
                "status": "ok",
                "passed": result.passed,
                "offending_line": None,
                "reason": result.reason,
            }

        resolved = _resolve_offending_line(result.offending_line, agent_texts)
        if resolved is not None:
            return {
                "rule": RULE_NAME,
                "status": "ok",
                "passed": result.passed,
                "offending_line": resolved,
                "reason": result.reason,
            }
        last_reason = f"model's offending_line was not a real agent line: {result.offending_line!r}"

    return {
        "rule": RULE_NAME,
        "status": "error",
        "passed": None,
        "offending_line": None,
        "reason": last_reason,
    }
