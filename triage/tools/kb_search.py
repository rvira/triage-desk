"""Keyword `kb_search` tool — top-3 knowledge-base retrieval.

Tier 1 retrieval is deliberately lexical: it has no API cost, is fully deterministic,
and therefore makes the eval numbers reproducible. Tier 2 swaps in embeddings behind
this same interface.
"""

from __future__ import annotations

import re
from typing import Any

from triage.data import load_articles

# Fixed-length token scan. No nested quantifiers, no alternation over overlapping
# prefixes, so untrusted ticket text cannot trigger catastrophic backtracking (CWE-1333).
_TOKEN_RE = re.compile(r"[a-z0-9]{2,32}")

MAX_QUERY_CHARS = 2000
TOP_K = 3

_STOPWORDS = frozenset(
    """
    a an the and or but if then than that this these those is are was were be been being
    do does did doing have has had having i me my we our you your it its they them their
    for to of in on at by with from as not no yes can cant cannot could would should will
    just very really please help hi hello thanks thank hey am im ive dont doesnt
    """.split()
)


def _tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokens, stopwords removed, input length capped."""
    if not isinstance(text, str):
        return set()
    clipped = text[:MAX_QUERY_CHARS].lower()
    return {t for t in _TOKEN_RE.findall(clipped) if t not in _STOPWORDS}


def _score(query_tokens: set[str], article: dict[str, Any]) -> float:
    """Overlap coefficient, with title matches weighted double.

    Normalising by query size keeps long articles from dominating purely by length.
    """
    if not query_tokens:
        return 0.0
    title_tokens = _tokenize(str(article.get("title", "")))
    body_tokens = _tokenize(str(article.get("body", "")))
    title_hits = len(query_tokens & title_tokens)
    body_hits = len(query_tokens & body_tokens)
    return (2 * title_hits + body_hits) / len(query_tokens)


def search_kb(query: str, top_k: int = TOP_K) -> list[dict[str, Any]]:
    """Return the top-k articles for a query, best first.

    Plain function so it is testable and callable without CrewAI installed.
    """
    top_k = max(1, min(int(top_k), 10))
    query_tokens = _tokenize(query)
    scored = [
        (_score(query_tokens, article), article)
        for article in load_articles()
    ]
    scored = [pair for pair in scored if pair[0] > 0.0]
    # Sort by score desc, then id asc, so ties are deterministic across runs.
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("id", ""))))
    return [
        {
            "id": article.get("id"),
            "category": article.get("category"),
            "title": article.get("title"),
            "body": article.get("body"),
            "score": round(score, 4),
        }
        for score, article in scored[:top_k]
    ]


def format_results(results: list[dict[str, Any]]) -> str:
    """Render results for the agent prompt. Plain text only — never executed."""
    if not results:
        return "NO_MATCHES"
    lines = []
    for r in results:
        lines.append(f"- {r['id']} [{r['category']}] {r['title']}\n  {r['body']}")
    return "\n".join(lines)


def build_tool():  # pragma: no cover - requires crewai installed
    """Wrap `search_kb` as a CrewAI tool.

    Imported lazily so the rest of the package (schema, gate, eval) stays usable and
    testable without the crewai dependency present.
    """
    from crewai.tools import tool

    @tool("kb_search")
    def kb_search(query: str) -> str:
        """Search the CloudNote knowledge base. Input: a short query of keywords
        describing the customer's problem. Returns the top 3 matching articles with
        their ids, titles and bodies, or NO_MATCHES."""
        return format_results(search_kb(query))

    return kb_search
