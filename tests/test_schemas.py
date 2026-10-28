import pytest
from pydantic import ValidationError

from app.schemas import Classification, EmailAnalysis, JSONAnalysis, PDFAnalysis


def test_classification_accepts_valid_output():
    c = Classification(input_type="email", business_intent="Complaint", confidence=0.9,
                       metadata={"urgency": "high"})
    assert c.metadata.urgency == "high"


def test_classification_metadata_defaults_and_keeps_extra_keys():
    c = Classification(input_type="json", business_intent="Invoice", confidence=0.7)
    assert c.metadata.urgency == "medium"
    c = Classification(input_type="json", business_intent="Invoice", confidence=0.7,
                       metadata={"urgency": "low", "field_count": 3})
    assert c.model_dump()["metadata"]["field_count"] == 3


@pytest.mark.parametrize("bad", [
    {"input_type": "docx", "business_intent": "Invoice", "confidence": 0.5},
    {"input_type": "pdf", "business_intent": None, "confidence": 0.5},
    {"input_type": "pdf", "business_intent": "Invoice", "confidence": 1.5},
])
def test_classification_rejects_invalid_output(bad):
    with pytest.raises(ValidationError):
        Classification(**bad)


def test_email_analysis_restricts_labels():
    ok = {"tone": "urgent", "urgency": "high", "sentiment": "negative",
          "key_topics": [], "action_items": [], "entities": {}}
    EmailAnalysis(**ok)
    with pytest.raises(ValidationError):
        EmailAnalysis(**{**ok, "urgency": "very high"})


def test_json_analysis_shape():
    a = JSONAnalysis(
        schema_analysis={"required_fields": ["a"], "field_types": {"a": "str"}},
        data_quality={"completeness": 1, "consistency": 0.5},
        business_context={"type": "webhook", "priority": "high", "action_required": True},
    )
    assert a.business_context.priority.value == "high"


def test_pdf_analysis_shape():
    a = PDFAnalysis(
        document_type="invoice",
        line_items=[{"description": "License", "amount": 10.0}],
        totals={"subtotal": 10.0, "total": 11.0},
        compliance={"keywords_found": ["gdpr"], "risk_level": "low"},
    )
    assert a.totals.currency == "USD"
    with pytest.raises(ValidationError):
        PDFAnalysis(document_type="memo", compliance={"risk_level": "low"})
