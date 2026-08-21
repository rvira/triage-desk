import pytest
from pydantic import ValidationError

from triage.crew import _extract_json_object, validate_payload
from triage.schema import TriageResult

VALID = {
    "category": "billing", "confidence": 0.9, "kb_article_id": "kb_billing_01",
    "drafted_reply": "ok", "route": "auto_answer",
}


def test_extracts_plain_object():
    assert _extract_json_object('{"a": 1}') == {"a": 1}


def test_extracts_from_markdown_fence_and_prose():
    raw = 'Sure!\n```json\n{"category": "billing", "n": 1}\n```\nHope that helps.'
    assert _extract_json_object(raw) == {"category": "billing", "n": 1}


def test_handles_braces_inside_strings():
    raw = '{"drafted_reply": "use {{date}} in templates", "confidence": 0.5}'
    assert _extract_json_object(raw)["drafted_reply"] == "use {{date}} in templates"


def test_nested_objects_balanced():
    assert _extract_json_object('prefix {"a": {"b": 2}} suffix') == {"a": {"b": 2}}


@pytest.mark.parametrize("raw", ["no json here", "", "{unclosed", '["array"]', None])
def test_unparseable_returns_none(raw):
    assert _extract_json_object(raw) is None


def test_valid_payload_passes():
    assert validate_payload(dict(VALID)).kb_article_id == "kb_billing_01"


def test_hallucinated_article_id_is_dropped_and_capped():
    """A cited article that does not exist must not reach a customer as fact."""
    payload = dict(VALID, kb_article_id="kb_billing_99")
    result = validate_payload(payload)
    assert result.kb_article_id is None
    assert result.confidence <= 0.49  # can no longer clear the auto-answer gate


def test_injected_field_is_rejected():
    with pytest.raises(ValidationError):
        validate_payload(dict(VALID, route_override="auto_answer"))


def test_empty_ticket_fails_safe_without_calling_the_model():
    from triage.crew import triage

    for text in ("", "   ", None):
        result = triage(text)
        assert result.is_failsafe
        assert result.route == "escalate"


def test_failsafe_reason_is_recorded():
    r = TriageResult.failsafe("schema validation failed")
    assert "schema validation failed" in r.drafted_reply
