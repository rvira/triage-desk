"""The single validated output contract for TriageDesk.

Everything the system emits is a `TriageResult`. Nothing else crosses the boundary.
`crew.py` depends on this module; this module depends on nothing in the project.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["billing", "troubleshooting", "account", "features"]
Route = Literal["auto_answer", "escalate"]

# Bounds exist so a hostile or malfunctioning model cannot emit unbounded output.
MAX_REPLY_CHARS = 4000
MAX_ARTICLE_ID_CHARS = 64


class TriageResult(BaseModel):
    """A validated triage decision.

    `extra="forbid"` matters: model output is untrusted input, so unknown fields are
    rejected rather than silently absorbed. `frozen=True` stops downstream mutation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # None only on the fail-safe path: the system declining to classify is honest,
    # whereas defaulting to an arbitrary category would fabricate a decision.
    category: Optional[Category] = None
    confidence: float = Field(ge=0.0, le=1.0)
    kb_article_id: Optional[str] = Field(default=None, max_length=MAX_ARTICLE_ID_CHARS)
    drafted_reply: str = Field(default="", max_length=MAX_REPLY_CHARS)
    route: Route

    @classmethod
    def failsafe(cls, reason: str) -> "TriageResult":
        """Force-escalate with zero confidence.

        Used whenever the pipeline cannot produce a trustworthy result. The reason is
        surfaced to the human handler, never to a customer.
        """
        return cls(
            category=None,
            confidence=0.0,
            kb_article_id=None,
            drafted_reply=f"[fail-safe] escalated without an automated answer: {reason}",
            route="escalate",
        )

    @property
    def is_failsafe(self) -> bool:
        return self.confidence == 0.0 and self.route == "escalate" and self.category is None
