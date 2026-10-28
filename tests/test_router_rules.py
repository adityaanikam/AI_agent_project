import json
from pathlib import Path

import httpx
import pytest

from app.core.router import ActionRouter

SAMPLE_JSON = json.loads(Path("test_sample.json").read_text())


def json_agent_output(parsed):
    # Shape returned by the JSON agent
    return {
        "status": "success",
        "analysis": {"business_context": {"priority": "medium"}},
        "schema_validation": {},
        "anomalies": [],
        "parsed_data": parsed,
    }


def pdf_agent_output(keywords_found, risk_level):
    # Shape returned by the PDF agent
    return {
        "status": "success",
        "analysis": {"document_type": "contract"},
        "compliance_check": {"keywords_found": keywords_found, "risk_level": risk_level},
        "metadata": {"page_count": 1},
        "raw_text": "...",
    }


def types(planned):
    return [a["type"] for a in planned]


def test_high_value_amount_nested_under_data_triggers_risk_alert():
    planned = ActionRouter().plan_actions(json_agent_output(SAMPLE_JSON))
    assert types(planned) == ["risk_alert"]
    assert planned[0]["payload"]["amount"] == 15000.00


def test_high_value_amount_at_top_level_triggers_risk_alert():
    planned = ActionRouter().plan_actions(json_agent_output({"amount": 20000}))
    assert types(planned) == ["risk_alert"]


def test_amount_at_threshold_or_non_numeric_is_ignored():
    router = ActionRouter()
    assert router.plan_actions(json_agent_output({"amount": 10000})) == []
    assert router.plan_actions(json_agent_output({"amount": "99999"})) == []
    assert router.plan_actions(json_agent_output({"amount": True})) == []
    assert router.plan_actions(json_agent_output([1, 2, 3])) == []


def test_legacy_data_key_is_not_read():
    # The old rule read agent_output["data"]; no agent produces that key.
    output = {"status": "success", "analysis": {}, "data": {"amount": 50000}}
    assert ActionRouter().plan_actions(output) == []


def test_pdf_without_compliance_keywords_triggers_nothing():
    assert ActionRouter().plan_actions(pdf_agent_output({}, "low")) == []


def test_pdf_with_gdpr_triggers_exactly_one_compliance_action():
    planned = ActionRouter().plan_actions(pdf_agent_output({"GDPR": ["gdpr"]}, "medium"))
    assert types(planned) == ["compliance"]
    assert planned[0]["payload"]["alert_type"] == "gdpr_mention"


def test_pdf_with_other_keywords_is_flagged_without_gdpr_label():
    planned = ActionRouter().plan_actions(pdf_agent_output({"PCI": ["credit card"]}, "medium"))
    assert types(planned) == ["compliance"]
    assert planned[0]["payload"]["alert_type"] == "compliance_keywords"


def test_high_urgency_email_triggers_notification_with_subject():
    output = {
        "status": "success",
        "metadata": {"subject": "URGENT: outage"},
        "analysis": {"urgency": "high"},
    }
    planned = ActionRouter().plan_actions(output)
    assert types(planned) == ["notification"]
    assert planned[0]["payload"]["message"] == "URGENT: outage"


def test_fields_no_agent_produces_trigger_nothing():
    # risk_score, compliance_issues and customer_data were read by the old
    # router but are produced by no agent; those rules were removed.
    output = {
        "status": "success",
        "analysis": {"risk_score": 0.99, "compliance_issues": ["x"], "customer_data": {"id": 1}},
    }
    assert ActionRouter().plan_actions(output) == []


def test_send_posts_payload_to_the_action_endpoint():
    seen = []

    def handler(request):
        seen.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json={"status": "ok"})

    router = ActionRouter(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert router.send("risk_alert", {"amount": 1}) == {"status": "ok"}
    assert seen == [(router.endpoints["risk_alert"], {"amount": 1})]


def test_send_raises_on_error_status_and_unknown_type():
    router = ActionRouter(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    with pytest.raises(httpx.HTTPStatusError):
        router.send("crm", {})
    with pytest.raises(ValueError):
        router.send("fax", {})


def test_mock_response_is_marked_as_mock():
    response = ActionRouter().mock_response("compliance", {})
    assert response["mock"] is True
    assert response["review_status"] == "scheduled"
