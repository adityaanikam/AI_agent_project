import json
from pathlib import Path

import httpx
import pytest

from app.core.memory import MemoryManager
from app.core.router import ActionRouter
from app.graph import Agents, GraphRunner, GraphSettings, RunStateError, build_graph, sqlite_checkpointer
from app.llm import FakeChatModel
from scripts.make_text_pdf import make_pdf

SAMPLE_EMAIL = Path("test_sample.eml").read_bytes()
SAMPLE_JSON = Path("test_sample.json").read_bytes()

EMAIL_CLASS = {"input_type": "email", "business_intent": "Complaint", "confidence": 0.9,
               "metadata": {"urgency": "high"}}
JSON_CLASS = {"input_type": "json", "business_intent": "Invoice", "confidence": 0.9}
PDF_CLASS = {"input_type": "pdf", "business_intent": "Regulation", "confidence": 0.9}
EMAIL_ANALYSIS = {"tone": "urgent", "urgency": "high", "sentiment": "negative",
                  "key_topics": [], "action_items": [], "entities": {}}


class Harness:
    """A runner over temp SQLite files, a fake model and a fake HTTP endpoint"""

    def __init__(self, tmp_path, responses=(), handler=None, settings=None):
        self.tmp_path = tmp_path
        self.llm = FakeChatModel(responses=list(responses))
        self.requests = []
        self.sleeps = []
        self.handler = handler or (lambda request: httpx.Response(200, json={"status": "ok"}))
        self.settings = settings or GraphSettings(retry_base_delay=1.0)
        self.memory = MemoryManager(f"sqlite:///{tmp_path / 'records.db'}")
        self.runner = self.new_runner()

    def _handle(self, request):
        self.requests.append((str(request.url), json.loads(request.content)))
        return self.handler(request)

    def new_runner(self, router=None):
        """A runner with a fresh graph on the same files, like after a restart"""
        router = router or ActionRouter(sync_client=httpx.Client(transport=httpx.MockTransport(self._handle)))
        graph = build_graph(Agents.with_llm(self.llm), router, self.settings,
                            checkpointer=sqlite_checkpointer(str(self.tmp_path / "checkpoints.db")),
                            sleep=self.sleeps.append)
        return GraphRunner(graph, self.memory)

    def start(self, filename, content, process_id="p1"):
        self.memory.create_record(process_id, "unknown", {"filename": filename})
        return self.runner.start(process_id, filename, content)

    def record(self, process_id="p1"):
        return self.memory.get_record(process_id)

    def state(self, process_id="p1"):
        return self.runner.graph.get_state(GraphRunner.config(process_id)).values


def test_confident_email_runs_end_to_end(tmp_path):
    h = Harness(tmp_path, [EMAIL_CLASS, EMAIL_ANALYSIS])
    assert h.start("mail.eml", SAMPLE_EMAIL) == "completed"
    record = h.record()
    assert record.classification["input_type"] == "email"
    assert record.agent_output["analysis"]["urgency"] == "high"
    assert [a["action"] for a in record.actions_triggered] == ["notification"]
    assert h.requests[0][1]["priority"] == "high"
    assert h.state()["classification_source"] == "llm"


def test_parse_failure_goes_to_repair_node(tmp_path):
    h = Harness(tmp_path, ["```json {bad```", EMAIL_CLASS, EMAIL_ANALYSIS])
    assert h.start("mail.eml", SAMPLE_EMAIL) == "completed"
    assert h.state()["classification_source"] == "repair"
    repair_prompt = h.llm.calls[1]
    assert "{bad" in repair_prompt[-2].content


def test_failed_repair_goes_to_heuristic_then_waits_for_review(tmp_path):
    h = Harness(tmp_path, ["bad", "still bad"])
    assert h.start("mail.eml", SAMPLE_EMAIL) == "awaiting_review"
    assert h.state()["classification_source"] == "heuristic"
    assert h.record().status == "awaiting_review"
    request = h.runner.pending_review("p1")
    assert request["kind"] == "classification"
    assert request["classification"]["input_type"] == "email"
    assert len(h.llm.calls) == 2  # classify + repair, no agent yet

    h.llm.responses.append(EMAIL_ANALYSIS)
    assert h.runner.review("p1", {"approved": True}) == "completed"
    assert h.record().classification["reviewed"] is True
    assert h.state()["reviews"] == [{"kind": "classification", "approved": True}]


def test_unreachable_model_skips_repair(tmp_path):
    h = Harness(tmp_path, [ConnectionError("refused")])
    assert h.start("mail.eml", SAMPLE_EMAIL) == "awaiting_review"
    assert h.state()["classification_source"] == "heuristic"
    assert len(h.llm.calls) == 1


def test_rejected_classification_stops_the_run(tmp_path):
    h = Harness(tmp_path, ["bad", "bad"])
    h.start("mail.eml", SAMPLE_EMAIL)
    assert h.runner.review("p1", {"approved": False}) == "rejected"
    assert h.record().agent_output is None
    assert h.requests == []


def test_reviewer_can_override_input_type(tmp_path):
    h = Harness(tmp_path, ["bad", "bad"])
    assert h.start("data.txt", b'{"note": "hello"}') == "awaiting_review"
    assert h.runner.review("p1", {"approved": True, "input_type": "json"}) == "completed"
    assert h.state()["classification_source"] == "review"
    assert h.record().agent_output["parsed_data"] == {"note": "hello"}


def test_unknown_input_type_ends_with_error(tmp_path):
    h = Harness(tmp_path, ["bad", "bad"], settings=GraphSettings(min_confidence=0.0))
    assert h.start("notes.txt", b"just some words") == "error"
    assert h.record().error == "Unsupported input type: unknown"


def test_agent_failure_ends_with_error(tmp_path):
    h = Harness(tmp_path, [JSON_CLASS])
    assert h.start("data.json", b"{not json") == "error"
    assert h.record().error.startswith("Agent processing failed: Invalid JSON")


def test_risky_action_waits_for_approval_then_is_sent(tmp_path):
    h = Harness(tmp_path, [JSON_CLASS])
    assert h.start("data.json", SAMPLE_JSON) == "awaiting_review"
    request = h.runner.pending_review("p1")
    assert request["kind"] == "actions"
    assert request["actions"][0]["type"] == "risk_alert"
    assert request["actions"][0]["payload"]["amount"] == 15000.0
    assert h.requests == []

    assert h.runner.review("p1", {"approved": True, "note": "ok"}) == "completed"
    assert h.requests[0][1]["alert_type"] == "high_value_transaction"
    assert h.record().actions_triggered[0]["response"] == {"status": "ok"}


def test_rejected_risky_action_is_skipped(tmp_path):
    h = Harness(tmp_path, [JSON_CLASS])
    h.start("data.json", SAMPLE_JSON)
    assert h.runner.review("p1", {"approved": False}) == "completed"
    assert h.requests == []
    assert h.record().actions_triggered == [
        {"action": "risk_alert", "status": "skipped", "reason": "rejected in review"}]


def test_gdpr_pdf_compliance_action_needs_approval(tmp_path):
    h = Harness(tmp_path, [PDF_CLASS])
    pdf = make_pdf(["Data processing agreement", "Subject to GDPR."])
    assert h.start("dpa.pdf", pdf) == "awaiting_review"
    assert h.runner.pending_review("p1")["actions"][0]["type"] == "compliance"


def test_review_is_refused_when_not_waiting(tmp_path):
    h = Harness(tmp_path, [EMAIL_CLASS, EMAIL_ANALYSIS])
    h.start("mail.eml", SAMPLE_EMAIL)
    with pytest.raises(RunStateError):
        h.runner.review("p1", {"approved": True})


def test_failed_action_is_retried_through_the_loop_edge(tmp_path):
    failures = iter([503, 503])
    h = Harness(tmp_path, [EMAIL_CLASS, EMAIL_ANALYSIS],
                handler=lambda r: httpx.Response(next(failures, 200), json={"status": "ok"}))
    assert h.start("mail.eml", SAMPLE_EMAIL) == "completed"
    assert len(h.requests) == 3
    assert h.sleeps == [1.0, 2.0]
    assert h.record().actions_triggered[0]["attempts"] == 3


def test_action_falls_back_to_mock_after_three_retries(tmp_path):
    h = Harness(tmp_path, [EMAIL_CLASS, EMAIL_ANALYSIS], handler=lambda r: httpx.Response(500))
    assert h.start("mail.eml", SAMPLE_EMAIL) == "completed"
    assert len(h.requests) == 4
    assert h.sleeps == [1.0, 2.0, 4.0]
    action = h.record().actions_triggered[0]
    assert action["attempts"] == 4
    assert action["response"]["mock"] is True


class CrashOnceRouter(ActionRouter):
    """Raises a non-HTTP error on the first send, as if the process died"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.crashed = False

    def send(self, action_type, data):
        if not self.crashed:
            self.crashed = True
            raise RuntimeError("worker crashed")
        return super().send(action_type, data)


def test_crashed_run_resumes_from_checkpoint_after_restart(tmp_path):
    h = Harness(tmp_path, [EMAIL_CLASS, EMAIL_ANALYSIS])
    h.runner = h.new_runner(router=CrashOnceRouter(sync_client=httpx.Client(transport=httpx.MockTransport(h._handle))))
    assert h.start("mail.eml", SAMPLE_EMAIL) == "error"
    assert h.record().error == "worker crashed"
    assert len(h.llm.calls) == 2

    restarted = h.new_runner()
    assert restarted.can_resume("p1")
    assert restarted.resume("p1") == "completed"
    assert h.record().error is None
    assert len(h.llm.calls) == 2  # classify and agent were not run again
    assert [a["action"] for a in h.record().actions_triggered] == ["notification"]


def test_resume_incomplete_picks_up_unfinished_runs(tmp_path):
    h = Harness(tmp_path, [EMAIL_CLASS, EMAIL_ANALYSIS])
    h.runner = h.new_runner(router=CrashOnceRouter(sync_client=httpx.Client(transport=httpx.MockTransport(h._handle))))
    h.start("mail.eml", SAMPLE_EMAIL)
    # A killed process never gets to write "error"; its record stays mid-way
    h.memory.update_record("p1", {"status": "processed", "error": None})
    h.memory.create_record("p2", "unknown", {})  # killed before any checkpoint

    restarted = h.new_runner()
    assert restarted.resume_incomplete() == ["p1"]
    assert h.record("p1").status == "completed"
    assert h.record("p2").status == "error"


def test_paused_runs_are_not_auto_resumed(tmp_path):
    h = Harness(tmp_path, [JSON_CLASS])
    h.start("data.json", SAMPLE_JSON)
    assert h.new_runner().resume_incomplete() == []
    assert h.record().status == "awaiting_review"


def test_classification_only_graph_never_interrupts():
    graph = build_graph(Agents.with_llm(FakeChatModel()), classification_only=True)
    out = graph.invoke({"filename": "x.json", "content": SAMPLE_JSON})
    assert out["classification"]["input_type"] == "json"
    assert out["classification_source"] == "heuristic"
    assert "agent_output" not in out
