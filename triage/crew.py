"""The CrewAI classifier crew and the fail-safe `triage()` orchestrator.

Safety model: the LLM is an untrusted component. Its output is parsed defensively,
validated against `TriageResult`, cross-checked against the real article ids, and on
any failure the pipeline force-escalates instead of guessing.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from pydantic import ValidationError

from triage.data import article_ids
from triage.schema import TriageResult
from triage.tools.kb_search import format_results, search_kb

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # per spec: re-ask at most twice, then fail safe
MAX_TICKET_CHARS = 8000
DEFAULT_MODEL = "gemini/gemini-2.5-flash"

_SYSTEM_RULES = """\
You are the CloudNote support triage classifier.

CloudNote is a SaaS note-taking product. You receive one customer ticket and the top
knowledge-base matches for it. Decide the category, pick the single best article, draft
a short reply, and decide whether the ticket can be auto-answered.

Rules:
- Reply with ONE JSON object and nothing else. No prose, no markdown fences.
- Keys exactly: category, confidence, kb_article_id, drafted_reply, route
- category: one of "billing", "troubleshooting", "account", "features"
- confidence: number between 0.0 and 1.0
- kb_article_id: an id copied verbatim from the provided matches, or null if none apply
- drafted_reply: <= 900 characters, addressed to the customer
- route: "escalate" if the ticket demands a refund, threatens legal action, reports
  data loss, reports a security incident, requests account/data deletion under privacy
  law, or is abusive. Otherwise "auto_answer".
- Never invent an article id. If the matches do not answer the ticket, set
  kb_article_id to null and lower your confidence.
"""

_USER_TEMPLATE = """\
TICKET:
{ticket}

KNOWLEDGE-BASE MATCHES:
{matches}

Return the JSON object now.
"""


def _extract_json_object(raw: str) -> Optional[dict[str, Any]]:
    """Pull the first balanced JSON object out of a model response.

    Hand-written scanner rather than a regex: brace matching is not a regular language,
    and a backtracking pattern over untrusted text risks ReDoS.
    """
    if not isinstance(raw, str):
        return None
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(raw)):
        char = raw[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start : index + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


def validate_payload(payload: dict[str, Any]) -> TriageResult:
    """Validate a candidate payload, rejecting hallucinated article ids.

    Raises `ValidationError` on anything that does not satisfy the contract.
    """
    result = TriageResult.model_validate(payload)
    if result.kb_article_id is not None and result.kb_article_id not in article_ids():
        # The model cited an article that does not exist. Keep the rest of the decision
        # but drop the false citation and cap confidence so it cannot auto-answer.
        logger.warning("dropping unknown kb_article_id from model output")
        result = TriageResult(
            category=result.category,
            confidence=min(result.confidence, 0.49),
            kb_article_id=None,
            drafted_reply=result.drafted_reply,
            route=result.route,
        )
    return result


def _build_crew(model: str):  # pragma: no cover - requires crewai + credentials
    """Construct the single-agent classifier crew."""
    from crewai import Agent, Crew, LLM, Process, Task

    from triage.tools.kb_search import build_tool

    llm = LLM(model=model, temperature=0.1)
    classifier = Agent(
        role="CloudNote Support Triage Classifier",
        goal="Turn one raw ticket into a single validated JSON triage decision.",
        backstory=(
            "A meticulous support engineer who answers only from the knowledge base, "
            "never invents article ids, and escalates anything sensitive."
        ),
        llm=llm,
        tools=[build_tool()],
        allow_delegation=False,
        verbose=False,
    )
    task = Task(
        description="{prompt}",
        expected_output="One JSON object with the five required keys and nothing else.",
        agent=classifier,
    )
    return Crew(agents=[classifier], tasks=[task], process=Process.sequential, verbose=False)


def _require_credentials() -> str:
    """Read the model name and assert a key is present.

    Credentials come from the environment only — never from source or a committed file.
    """
    if not os.environ.get("GOOGLE_API_KEY"):
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and populate it, "
            "or export the variable before running."
        )
    model = os.environ.get("TRIAGE_MODEL") or DEFAULT_MODEL
    if not isinstance(model, str) or not model or len(model) > 128:
        raise RuntimeError("TRIAGE_MODEL is not a valid model identifier")
    return model


def triage(ticket_text: str) -> TriageResult:
    """Triage one ticket, failing safe on any untrustworthy outcome.

    Never raises for model misbehaviour: a malformed or invalid response after
    `MAX_RETRIES` re-asks becomes a forced escalation with confidence 0.0.
    """
    if not isinstance(ticket_text, str) or not ticket_text.strip():
        return TriageResult.failsafe("empty ticket text")

    clipped = ticket_text[:MAX_TICKET_CHARS]
    matches = format_results(search_kb(clipped))
    prompt = "\n\n".join([_SYSTEM_RULES, _USER_TEMPLATE.format(ticket=clipped, matches=matches)])

    try:
        model = _require_credentials()
        crew = _build_crew(model)
    except Exception as exc:  # configuration or import failure
        logger.error("triage setup failed: %s", type(exc).__name__)
        return TriageResult.failsafe(f"setup failure ({type(exc).__name__})")

    last_problem = "unknown"
    for attempt in range(MAX_RETRIES + 1):
        try:
            raw = str(crew.kickoff(inputs={"prompt": prompt}))
        except Exception as exc:  # network, quota, provider error
            last_problem = f"model call failed ({type(exc).__name__})"
            logger.warning("attempt %d: %s", attempt + 1, last_problem)
            continue

        payload = _extract_json_object(raw)
        if payload is None:
            last_problem = "response contained no JSON object"
            logger.warning("attempt %d: %s", attempt + 1, last_problem)
            continue

        try:
            return validate_payload(payload)
        except ValidationError as exc:
            last_problem = f"schema validation failed ({exc.error_count()} errors)"
            logger.warning("attempt %d: %s", attempt + 1, last_problem)

    return TriageResult.failsafe(f"{last_problem} after {MAX_RETRIES + 1} attempts")
