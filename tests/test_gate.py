import io

from triage.gate import GateOutcome, classify, prompt_human
from triage.schema import TriageResult


def _result(confidence: float, route: str = "auto_answer") -> TriageResult:
    return TriageResult(
        category="billing", confidence=confidence,
        kb_article_id="kb_billing_01", drafted_reply="reply", route=route,
    )


def test_high_confidence_auto_answers():
    assert classify(_result(0.95)) is GateOutcome.AUTO_ANSWER
    assert classify(_result(0.80)) is GateOutcome.AUTO_ANSWER


def test_medium_confidence_needs_human():
    assert classify(_result(0.79)) is GateOutcome.HUMAN_APPROVE
    assert classify(_result(0.50)) is GateOutcome.HUMAN_APPROVE


def test_low_confidence_escalates():
    assert classify(_result(0.49)) is GateOutcome.ESCALATE
    assert classify(_result(0.0)) is GateOutcome.ESCALATE


def test_model_escalation_is_never_downgraded():
    """The gate may only be more cautious than the decision it receives."""
    assert classify(_result(0.99, route="escalate")) is GateOutcome.ESCALATE


def test_failsafe_escalates():
    assert classify(TriageResult.failsafe("bad json")) is GateOutcome.ESCALATE


def test_human_approval_accepts_yes():
    assert prompt_human(_result(0.6), stdin=io.StringIO("y\n"), stdout=io.StringIO()) is True


def test_human_approval_defaults_to_reject():
    for answer in ("n\n", "\n", "maybe\nmaybe\nmaybe\n"):
        assert prompt_human(
            _result(0.6), stdin=io.StringIO(answer), stdout=io.StringIO()
        ) is False


def test_eof_is_rejection():
    """A closed stdin must not be read as approval."""
    assert prompt_human(_result(0.6), stdin=io.StringIO(""), stdout=io.StringIO()) is False
