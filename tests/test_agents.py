from pathlib import Path

from app.agents.classifier_agent import ClassifierAgent
from app.agents.email_agent import EmailAgent
from app.agents.json_agent import JSONAgent
from app.agents.pdf_agent import PDFAgent
from app.llm import FakeChatModel
from scripts.make_text_pdf import make_pdf

SAMPLE_EMAIL = Path("test_sample.eml").read_text()
SAMPLE_JSON = Path("test_sample.json").read_text()

EMAIL_ANALYSIS = {
    "tone": "urgent", "urgency": "high", "sentiment": "negative",
    "key_topics": ["outage"], "action_items": ["escalate"], "entities": {"people": []},
}
JSON_ANALYSIS = {
    "schema_analysis": {"required_fields": ["event_type"], "optional_fields": [], "field_types": {}},
    "anomalies": [],
    "data_quality": {"completeness": 1.0, "consistency": 1.0, "issues": []},
    "business_context": {"type": "webhook", "priority": "high", "action_required": True},
}
PDF_ANALYSIS = {
    "document_type": "invoice",
    "line_items": [{"description": "License", "amount": 1200.0}],
    "totals": {"subtotal": 1200.0, "total": 1200.0},
    "compliance": {"keywords_found": [], "risk_level": "low"},
}


# Classifier

def test_classifier_uses_model_answer():
    llm = FakeChatModel(responses=[{"input_type": "email", "business_intent": "Complaint",
                                    "confidence": 0.95, "metadata": {"urgency": "high"}}])
    result = ClassifierAgent(llm).classify(SAMPLE_EMAIL)
    assert result["classification"]["input_type"] == "email"
    assert result["classification"]["confidence"] == 0.95
    assert "Content to classify" in llm.calls[0][-1].content


def test_classifier_repairs_then_uses_repaired_answer():
    llm = FakeChatModel(responses=[
        "```json\n{\"input_type\": \"email\"}\n```",
        {"input_type": "email", "business_intent": "Complaint", "confidence": 0.8},
    ])
    result = ClassifierAgent(llm).classify(SAMPLE_EMAIL)
    assert result["classification"]["business_intent"] == "Complaint"
    assert len(llm.calls) == 2


def test_classifier_falls_back_to_heuristic_after_failed_repair():
    llm = FakeChatModel(responses=["not json", "still not json"])
    result = ClassifierAgent(llm).classify(SAMPLE_JSON)
    assert result["classification"]["input_type"] == "json"
    assert result["classification"]["confidence"] == 0.5
    assert result["classification"]["metadata"]["amount"] == 15000.0


def test_classifier_falls_back_when_model_unreachable():
    llm = FakeChatModel(responses=[ConnectionError("refused")])
    result = ClassifierAgent(llm).classify(SAMPLE_EMAIL)
    assert result["status"] == "success"
    assert result["classification"]["input_type"] == "email"
    assert len(llm.calls) == 1  # no repair for an unreachable model


def test_heuristic_handles_json_array_mentioning_webhook():
    result = ClassifierAgent(FakeChatModel()).heuristic('[{"type": "webhook"}]')
    assert result["input_type"] == "json"
    assert result["metadata"]["field_count"] == 0


# Email agent

def test_email_agent_structured_analysis():
    out = EmailAgent(FakeChatModel(responses=[EMAIL_ANALYSIS])).process_email(SAMPLE_EMAIL)
    assert out["status"] == "success"
    assert out["analysis"]["urgency"] == "high"
    assert out["analysis_source"] == "llm"
    assert out["metadata"]["subject"] == "URGENT: System Outage in Production"


def test_email_agent_fallback_keeps_shape():
    out = EmailAgent(FakeChatModel()).process_email(SAMPLE_EMAIL)
    assert out["status"] == "success"
    assert out["analysis_source"] == "fallback"
    assert set(out["analysis"]) == {"tone", "urgency", "entities", "action_items", "sentiment", "key_topics"}


def test_plain_text_email_has_no_attachments():
    out = EmailAgent(FakeChatModel()).process_email(SAMPLE_EMAIL)
    assert out["metadata"]["has_attachments"] is False


def test_multipart_email_with_attachment_is_detected():
    raw = (
        "From: a@example.com\nTo: b@example.com\nSubject: files\n"
        "MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=XX\n\n"
        "--XX\nContent-Type: text/plain\n\nsee attached\n"
        "--XX\nContent-Type: application/pdf\nContent-Disposition: attachment; filename=a.pdf\n\nPDF\n"
        "--XX--\n"
    )
    out = EmailAgent(FakeChatModel()).process_email(raw)
    assert out["metadata"]["has_attachments"] is True
    assert out["raw_content"].strip() == "see attached"


# JSON agent

def test_json_agent_structured_analysis():
    out = JSONAgent(FakeChatModel(responses=[JSON_ANALYSIS])).process_json(SAMPLE_JSON)
    assert out["analysis"]["business_context"]["priority"] == "high"
    assert out["parsed_data"]["data"]["amount"] == 15000.0
    assert out["schema_validation"]["webhook"]["valid"] is True


def test_json_agent_fallback_and_invalid_input():
    out = JSONAgent(FakeChatModel()).process_json(SAMPLE_JSON)
    assert out["analysis_source"] == "fallback"
    assert "event_type" in out["analysis"]["schema_analysis"]["required_fields"]
    assert JSONAgent(FakeChatModel()).process_json("{not json")["status"] == "error"


def test_json_agent_accepts_top_level_array():
    out = JSONAgent(FakeChatModel()).process_json("[1, 2]")
    assert out["status"] == "success"
    assert out["anomalies"] == []


# PDF agent

def test_pdf_agent_structured_analysis_and_compliance():
    pdf = make_pdf(["INVOICE #12", "This contract covers GDPR data protection."])
    out = PDFAgent(FakeChatModel(responses=[PDF_ANALYSIS])).analyze_pdf(pdf)
    assert out["status"] == "success"
    assert out["analysis"]["document_type"] == "invoice"
    assert out["compliance_check"]["keywords_found"] == {"GDPR": ["gdpr", "data protection"]}
    assert out["metadata"]["page_count"] == 1


def test_pdf_agent_fallback_and_bad_bytes():
    out = PDFAgent(FakeChatModel()).analyze_pdf(make_pdf(["hello"]))
    assert out["analysis_source"] == "fallback"
    assert out["analysis"]["document_type"] == "other"
    assert PDFAgent(FakeChatModel()).analyze_pdf(b"not a pdf")["status"] == "error"
