"""Scripted eval over the 25-ticket labeled set.

Signature metric: escalation recall on the six must-escalate tickets. Missing one of
those means the system would have sent an automated reply to a refund demand, a legal
threat, a data-loss report, a security incident, a statutory erasure request, or an
abusive customer — so recall here is a safety measure, not an accuracy measure.

Two modes:
  --predictions FILE   score a saved predictions file. No API calls, no cost.
  --live               run the crew over every ticket. Spends model quota.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from triage.data import load_tickets
from triage.schema import TriageResult

ROOT = Path(__file__).resolve().parent.parent


def _load_predictions(path: str) -> dict[str, dict[str, Any]]:
    """Load {ticket_id: prediction} from a JSON file, containment-checked."""
    candidate = Path(path).resolve()
    if ROOT not in candidate.parents and candidate.parent != ROOT:
        raise ValueError("predictions file must live inside the project")
    with candidate.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("predictions file must be a JSON object keyed by ticket id")
    return raw


def _predict_live(tickets: tuple[dict[str, Any], ...]) -> dict[str, dict[str, Any]]:
    from triage.crew import triage  # imported lazily: costs quota

    out: dict[str, dict[str, Any]] = {}
    for ticket in tickets:
        result = triage(ticket["text"])
        out[ticket["id"]] = result.model_dump()
        print(f"  {ticket['id']} -> {result.route} ({result.confidence:.2f})", file=sys.stderr)
    return out


def score(
    tickets: tuple[dict[str, Any], ...],
    predictions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compute the metric block. Pure function — unit-testable with fixtures."""
    total = 0
    route_correct = 0
    category_correct = 0
    article_correct = 0

    must_escalate = 0
    caught_escalate = 0
    predicted_escalate = 0
    true_positive_escalate = 0

    per_trigger: Counter[str] = Counter()
    per_trigger_caught: Counter[str] = Counter()
    misses: list[dict[str, Any]] = []

    for ticket in tickets:
        prediction = predictions.get(ticket["id"])
        if prediction is None:
            continue
        # Predictions are untrusted input too: validate before scoring.
        result = TriageResult.model_validate(prediction)
        total += 1

        expected_route = ticket["expected_route"]
        if result.route == expected_route:
            route_correct += 1
        if result.category == ticket["expected_category"]:
            category_correct += 1
        if result.kb_article_id == ticket["expected_article"]:
            article_correct += 1

        if result.route == "escalate":
            predicted_escalate += 1
        if expected_route == "escalate":
            must_escalate += 1
            trigger = ticket.get("escalation_trigger") or "untagged"
            per_trigger[trigger] += 1
            if result.route == "escalate":
                caught_escalate += 1
                true_positive_escalate += 1
                per_trigger_caught[trigger] += 1
            else:
                misses.append(
                    {
                        "id": ticket["id"],
                        "trigger": trigger,
                        "predicted_route": result.route,
                        "confidence": result.confidence,
                    }
                )

    def ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    return {
        "scored_tickets": total,
        "escalation_recall": ratio(caught_escalate, must_escalate),
        "escalation_precision": ratio(true_positive_escalate, predicted_escalate),
        "routing_accuracy": ratio(route_correct, total),
        "category_accuracy": ratio(category_correct, total),
        "article_hit_rate": ratio(article_correct, total),
        "must_escalate_total": must_escalate,
        "must_escalate_caught": caught_escalate,
        "per_trigger_recall": {
            trigger: ratio(per_trigger_caught[trigger], count)
            for trigger, count in sorted(per_trigger.items())
        },
        "escalation_misses": misses,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run_eval")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--predictions", help="score a saved predictions JSON file (free)")
    mode.add_argument("--live", action="store_true", help="run the crew (spends quota)")
    parser.add_argument("--save", help="write live predictions to this path for re-scoring")
    args = parser.parse_args(argv)

    tickets = load_tickets()

    if args.live:
        predictions = _predict_live(tickets)
        if args.save:
            target = Path(args.save).resolve()
            if ROOT not in target.parents and target.parent != ROOT:
                print("error: --save path must be inside the project", file=sys.stderr)
                return 2
            target.write_text(json.dumps(predictions, indent=2), encoding="utf-8")
    else:
        predictions = _load_predictions(args.predictions)

    report = score(tickets, predictions)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if report["escalation_recall"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
