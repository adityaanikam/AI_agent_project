import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from app.core.router import ActionRouter
from app.graph import Agents, GraphRunner, GraphSettings, build_graph, sqlite_checkpointer
from app.llm import FakeChatModel

SAMPLE_EMAIL = Path("test_sample.eml").read_bytes()
SAMPLE_JSON = Path("test_sample.json").read_bytes()
EMAIL_CLASS = {"input_type": "email", "business_intent": "Complaint", "confidence": 0.9}
JSON_CLASS = {"input_type": "json", "business_intent": "Invoice", "confidence": 0.9}
EMAIL_ANALYSIS = {"tone": "urgent", "urgency": "high", "sentiment": "negative",
                  "key_topics": [], "action_items": [], "entities": {}}


class FlakyRouter(ActionRouter):
    def __init__(self, crash_first, **kwargs):
        super().__init__(**kwargs)
        self.crash_next = crash_first
        self.sent = []

    def send(self, action_type, data):
        if self.crash_next:
            self.crash_next = False
            raise RuntimeError("worker crashed")
        self.sent.append((action_type, data))
        return {"status": "ok"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    def install(responses, crash_first=False):
        llm = FakeChatModel(responses=list(responses))
        router = FlakyRouter(crash_first)
        graph = build_graph(Agents.with_llm(llm), router, GraphSettings(retry_base_delay=0),
                            checkpointer=sqlite_checkpointer(str(tmp_path / "cp.db")))
        monkeypatch.setattr(main, "runner", GraphRunner(graph, main.memory_manager))
        return router
    return install


def upload(client, name, content):
    response = client.post("/process", files={"file": (name, content)})
    assert response.status_code == 200
    return response.json()["process_id"]


def test_upload_runs_graph_and_status_reports_result(api):
    router = api([EMAIL_CLASS, EMAIL_ANALYSIS])
    client = TestClient(main.app)
    pid = upload(client, "mail.eml", SAMPLE_EMAIL)
    status = client.get(f"/status/{pid}").json()
    assert status["status"] == "completed"
    assert status["classification"]["input_type"] == "email"
    assert status["actions_triggered"][0]["action"] == "notification"
    assert status["review_request"] is None
    assert router.sent[0][0] == "notification"
    history = client.get("/history").json()["history"]
    assert pid in [h["process_id"] for h in history]


def test_risky_action_is_approved_through_review_endpoint(api):
    router = api([JSON_CLASS])
    client = TestClient(main.app)
    pid = upload(client, "data.json", SAMPLE_JSON)
    status = client.get(f"/status/{pid}").json()
    assert status["status"] == "awaiting_review"
    assert status["review_request"]["kind"] == "actions"
    assert router.sent == []

    response = client.post(f"/review/{pid}", json={"approved": True})
    assert response.status_code == 200
    assert client.get(f"/status/{pid}").json()["status"] == "completed"
    assert router.sent[0][0] == "risk_alert"


def test_low_confidence_classification_is_corrected_through_review(api):
    api(["bad", "bad"])
    client = TestClient(main.app)
    pid = upload(client, "notes.txt", b'{"note": "hi"}')
    status = client.get(f"/status/{pid}").json()
    assert status["review_request"]["kind"] == "classification"

    client.post(f"/review/{pid}", json={"approved": True, "input_type": "json"})
    status = client.get(f"/status/{pid}").json()
    assert status["status"] == "completed"
    assert status["agent_output"]["parsed_data"] == {"note": "hi"}


def test_review_endpoint_errors(api):
    api([EMAIL_CLASS, EMAIL_ANALYSIS])
    client = TestClient(main.app)
    pid = upload(client, "mail.eml", SAMPLE_EMAIL)
    assert client.post(f"/review/{pid}", json={"approved": True}).status_code == 409
    assert client.post("/review/missing", json={"approved": True}).status_code == 404
    assert client.post(f"/review/{pid}", json={"approved": True, "input_type": "docx"}).status_code == 422
    assert client.post(f"/review/{pid}", json={}).status_code == 422


def test_failed_run_resumes_through_resume_endpoint(api):
    router = api([EMAIL_CLASS, EMAIL_ANALYSIS], crash_first=True)
    client = TestClient(main.app)
    pid = upload(client, "mail.eml", SAMPLE_EMAIL)
    status = client.get(f"/status/{pid}").json()
    assert status["status"] == "error"
    assert status["error"] == "worker crashed"

    assert client.post(f"/resume/{pid}").status_code == 200
    status = client.get(f"/status/{pid}").json()
    assert status["status"] == "completed"
    assert status["error"] is None
    assert router.sent[0][0] == "notification"
    assert client.post(f"/resume/{pid}").status_code == 409


def test_root_serves_upload_page(api):
    api([])
    assert "FlowBit File Processing" in TestClient(main.app).get("/").text
