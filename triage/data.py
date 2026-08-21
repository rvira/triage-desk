"""Read-only loaders for the committed data assets.

Assets are JSON only. `json.load` is used deliberately — `pickle` and `yaml.load`
execute arbitrary objects and must never touch repo-supplied or user-supplied data.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MAX_ASSET_BYTES = 8 * 1024 * 1024  # cap so a huge file cannot exhaust memory


def _read_json(relative_path: str) -> Any:
    """Load a JSON asset from inside the project root.

    The resolved path is checked for containment so a crafted relative path cannot
    escape the repo (CWE-22).
    """
    candidate = (PROJECT_ROOT / relative_path).resolve()
    if candidate != PROJECT_ROOT and PROJECT_ROOT not in candidate.parents:
        raise ValueError("asset path escapes the project root")
    if not candidate.is_file():
        raise FileNotFoundError(f"missing data asset: {relative_path}")
    if candidate.stat().st_size > MAX_ASSET_BYTES:
        raise ValueError(f"data asset too large: {relative_path}")
    with candidate.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def load_articles() -> tuple[dict[str, Any], ...]:
    """The CloudNote knowledge base."""
    articles = _read_json("kb/articles.json")
    if not isinstance(articles, list):
        raise ValueError("kb/articles.json must contain a JSON array")
    return tuple(articles)


@lru_cache(maxsize=1)
def article_ids() -> frozenset[str]:
    """Allow-list of real article ids.

    Used to reject hallucinated `kb_article_id` values from the model.
    """
    return frozenset(str(a["id"]) for a in load_articles() if "id" in a)


@lru_cache(maxsize=1)
def load_tickets() -> tuple[dict[str, Any], ...]:
    tickets = _read_json("eval/tickets.json")
    if not isinstance(tickets, list):
        raise ValueError("eval/tickets.json must contain a JSON array")
    return tuple(tickets)


def ticket_text(ticket_id: str) -> str:
    """Return only the ticket text.

    Deliberately narrow: the runtime must never see `expected_*` labels, or the eval
    would be measuring leakage instead of performance.
    """
    if not isinstance(ticket_id, str) or not ticket_id.isalnum() or len(ticket_id) > 16:
        raise ValueError("ticket id must be short and alphanumeric")
    for ticket in load_tickets():
        if ticket.get("id") == ticket_id:
            text = ticket.get("text", "")
            if not isinstance(text, str):
                raise ValueError("ticket text must be a string")
            return text
    raise KeyError(f"unknown ticket id: {ticket_id}")
