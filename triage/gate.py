"""Confidence gate — the routing policy, expressed as code rather than a prompt.

Bands (PLAN.md Tier 2, on a 0.0-1.0 scale):
    >= 0.80  auto_answer    ship the drafted reply
    0.50-0.79 human_approve a person accepts or rejects at the CLI
    <  0.50  escalate       hand over with the assembled context

The schema's `route` stays two-valued per the W5 spec; the three-way band lives here so
the contract and the policy can evolve independently.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, TextIO

from triage.schema import TriageResult

AUTO_ANSWER_THRESHOLD = 0.80
HUMAN_APPROVE_THRESHOLD = 0.50


class GateOutcome(str, Enum):
    AUTO_ANSWER = "auto_answer"
    HUMAN_APPROVE = "human_approve"
    ESCALATE = "escalate"


def classify(result: TriageResult) -> GateOutcome:
    """Map a validated result onto a gate outcome.

    An explicit `route="escalate"` from the model always wins: the gate may only ever
    be more cautious than the decision it receives, never less.
    """
    if result.route == "escalate":
        return GateOutcome.ESCALATE
    if result.confidence >= AUTO_ANSWER_THRESHOLD:
        return GateOutcome.AUTO_ANSWER
    if result.confidence >= HUMAN_APPROVE_THRESHOLD:
        return GateOutcome.HUMAN_APPROVE
    return GateOutcome.ESCALATE


def prompt_human(
    result: TriageResult,
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
    max_attempts: int = 3,
) -> bool:
    """Ask a human to approve the drafted reply. Returns True only on explicit approval.

    Streams are injectable so this is testable without a terminal. Anything other than
    a clear yes — including EOF or exhausted attempts — is treated as rejection.
    """
    import sys

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout

    print("\n--- HUMAN APPROVAL REQUIRED ---", file=stdout)
    print(f"category   : {result.category}", file=stdout)
    print(f"confidence : {result.confidence:.2f}", file=stdout)
    print(f"article    : {result.kb_article_id}", file=stdout)
    print(f"reply      : {result.drafted_reply}", file=stdout)

    for _ in range(max_attempts):
        print("approve? [y/N]: ", end="", file=stdout, flush=True)
        line = stdin.readline()
        if not line:  # EOF -> reject
            return False
        answer = line.strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no", ""}:
            return False
    return False
