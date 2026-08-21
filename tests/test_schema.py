import pytest
from pydantic import ValidationError

from triage.schema import TriageResult


def test_valid_result():
    r = TriageResult(
        category="billing", confidence=0.9, kb_article_id="kb_billing_01",
        drafted_reply="Here is how billing works.", route="auto_answer",
    )
    assert r.route == "auto_answer"
    assert not r.is_failsafe


def test_unknown_fields_rejected():
    """Model output is untrusted; extra keys must not be silently absorbed."""
    with pytest.raises(ValidationError):
        TriageResult(
            category="billing", confidence=0.5, drafted_reply="x",
            route="auto_answer", injected="payload",
        )


@pytest.mark.parametrize("bad", [-0.1, 1.1, 42])
def test_confidence_bounds(bad):
    with pytest.raises(ValidationError):
        TriageResult(category="billing", confidence=bad, drafted_reply="", route="escalate")


def test_invalid_enums_rejected():
    with pytest.raises(ValidationError):
        TriageResult(category="refunds", confidence=0.5, drafted_reply="", route="auto_answer")
    with pytest.raises(ValidationError):
        TriageResult(category="billing", confidence=0.5, drafted_reply="", route="send_it")


def test_reply_length_capped():
    with pytest.raises(ValidationError):
        TriageResult(
            category="billing", confidence=0.5, drafted_reply="x" * 5000, route="auto_answer",
        )


def test_failsafe_shape():
    r = TriageResult.failsafe("no json")
    assert r.route == "escalate"
    assert r.confidence == 0.0
    assert r.category is None
    assert r.is_failsafe


def test_result_is_frozen():
    r = TriageResult.failsafe("x")
    with pytest.raises(ValidationError):
        r.confidence = 1.0
