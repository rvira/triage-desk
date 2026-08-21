"""CLI entry point: ticket id in, validated TriageResult JSON out."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from triage.data import ticket_text
from triage.gate import GateOutcome, classify, prompt_human
from triage.schema import TriageResult


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m triage.run",
        description="Triage one CloudNote support ticket.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--ticket", help="ticket id from eval/tickets.json, e.g. t01")
    source.add_argument("--text", help="raw ticket text instead of a stored id")
    parser.add_argument(
        "--gate",
        action="store_true",
        help="apply the confidence gate (and prompt for approval in the medium band)",
    )
    parser.add_argument("--verbose", action="store_true", help="log retry detail to stderr")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.verbose else logging.ERROR,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        text = args.text if args.text is not None else ticket_text(args.ticket)
    except (KeyError, ValueError) as exc:
        # Generic message to stderr; no internals or stack trace.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    from triage.crew import triage  # imported here so --help works without crewai

    result: TriageResult = triage(text)
    payload = result.model_dump()

    if args.gate:
        outcome = classify(result)
        if outcome is GateOutcome.HUMAN_APPROVE:
            approved = prompt_human(result)
            outcome = GateOutcome.AUTO_ANSWER if approved else GateOutcome.ESCALATE
            payload["human_approved"] = approved
        payload["gate_outcome"] = outcome.value

    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
