"""
The processing pipeline as a LangGraph state graph

classify -> (repair_classification) -> (heuristic_classify)
         -> (review_classification) -> email_agent | json_agent | pdf_agent
         -> plan_actions -> (review_actions) -> dispatch_action (loops for retries)
         -> finalize
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, Optional

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.classifier_agent import ClassifierAgent
from app.agents.email_agent import EmailAgent
from app.agents.json_agent import JSONAgent
from app.agents.pdf_agent import PDFAgent
from app.core.router import ActionRouter
from app.graph.state import FlowState
from app.llm import StructuredResult

logger = logging.getLogger(__name__)

AGENT_NODES = {"email": "email_agent", "json": "json_agent", "pdf": "pdf_agent"}


@dataclass
class GraphSettings:
    """Tunable behaviour of the graph"""
    # Classifications below this confidence wait for human review
    min_confidence: float = 0.6
    # Action types that wait for human approval before they are sent
    risky_actions: FrozenSet[str] = field(default_factory=lambda: frozenset({"risk_alert", "compliance"}))
    # Retries per action after the first attempt, with exponential backoff
    max_retries: int = 3
    retry_base_delay: float = 1.0

    @classmethod
    def from_env(cls) -> "GraphSettings":
        risky = os.getenv("FLOWBIT_RISKY_ACTIONS", "risk_alert,compliance")
        return cls(
            min_confidence=float(os.getenv("FLOWBIT_MIN_CONFIDENCE", "0.6")),
            risky_actions=frozenset(a.strip() for a in risky.split(",") if a.strip()),
            max_retries=int(os.getenv("FLOWBIT_MAX_RETRIES", "3")),
            retry_base_delay=float(os.getenv("FLOWBIT_RETRY_BASE_DELAY", "1.0"))
        )


@dataclass
class Agents:
    """The four agents the graph calls"""
    classifier: ClassifierAgent
    email: EmailAgent
    json: JSONAgent
    pdf: PDFAgent

    @classmethod
    def with_llm(cls, llm: BaseChatModel) -> "Agents":
        return cls(ClassifierAgent(llm), EmailAgent(llm), JSONAgent(llm), PDFAgent(llm))


def decode_content(filename: str, content: bytes) -> str:
    """Text handed to the classifier"""
    if (filename or "").lower().endswith(".pdf"):
        return content.decode("utf-8", errors="ignore")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="ignore")


def _failed_reply(result: StructuredResult) -> Dict[str, Any]:
    return {"raw": result.raw, "error": result.error, "failure": result.failure}


def build_graph(
    agents: Agents,
    router: Optional[ActionRouter] = None,
    settings: Optional[GraphSettings] = None,
    checkpointer: Any = None,
    classification_only: bool = False,
    sleep: Callable[[float], None] = time.sleep
):
    """
    Compile the processing graph

    classification_only stops after classification, with no review, agents
    or actions; the classifier evaluation uses it.
    """
    settings = settings or GraphSettings()
    if router is None and not classification_only:
        router = ActionRouter()
    builder = StateGraph(FlowState)

    # Classification

    def classify(state: FlowState) -> Dict[str, Any]:
        text = decode_content(state.get("filename", ""), state["content"])
        result = agents.classifier.llm_classify(text)
        if result.ok:
            return {"text": text, "classification": result.parsed.model_dump(mode="json"),
                    "classification_source": "llm", "status": "classified"}
        return {"text": text, "llm_reply": _failed_reply(result)}

    def repair_classification(state: FlowState) -> Dict[str, Any]:
        reply = state["llm_reply"]
        failed = StructuredResult(None, reply["raw"], reply["error"], reply["failure"])
        result = agents.classifier.repair(state["text"], failed)
        if result.ok:
            return {"classification": result.parsed.model_dump(mode="json"),
                    "classification_source": "repair", "status": "classified"}
        return {"llm_reply": _failed_reply(result)}

    def heuristic_classify(state: FlowState) -> Dict[str, Any]:
        return {"classification": agents.classifier.heuristic(state["text"]),
                "classification_source": "heuristic", "status": "classified"}

    def review_classification(state: FlowState) -> Dict[str, Any]:
        classification = state["classification"]
        decision = dict(interrupt({
            "kind": "classification",
            "reason": f"confidence {classification['confidence']:.2f} is below {settings.min_confidence:.2f}",
            "classification": classification
        }) or {})
        reviews = state.get("reviews", []) + [{"kind": "classification", **decision}]
        if decision.get("approved") is not True:
            return {"reviews": reviews, "status": "rejected"}
        overrides = {k: decision[k] for k in ("input_type", "business_intent") if decision.get(k)}
        return {
            "reviews": reviews,
            "classification": {**classification, **overrides, "reviewed": True},
            "classification_source": "review" if overrides else state["classification_source"]
        }

    def to_agent(state: FlowState) -> str:
        return AGENT_NODES.get(state["classification"]["input_type"], "unsupported_input")

    def route_classified(state: FlowState) -> str:
        if classification_only:
            return END
        if state["classification"]["confidence"] < settings.min_confidence:
            return "review_classification"
        return to_agent(state)

    def after_classify(state: FlowState) -> str:
        if state.get("classification"):
            return route_classified(state)
        if state["llm_reply"]["failure"] == "parse":
            return "repair_classification"
        return "heuristic_classify"

    def after_repair(state: FlowState) -> str:
        if state.get("classification"):
            return route_classified(state)
        return "heuristic_classify"

    def after_review_classification(state: FlowState) -> str:
        if state.get("status") == "rejected":
            return END
        return to_agent(state)

    builder.add_node("classify", classify)
    builder.add_node("repair_classification", repair_classification)
    builder.add_node("heuristic_classify", heuristic_classify)
    builder.add_edge(START, "classify")

    if classification_only:
        builder.add_conditional_edges("classify", after_classify, ["repair_classification", "heuristic_classify", END])
        builder.add_conditional_edges("repair_classification", after_repair, ["heuristic_classify", END])
        builder.add_edge("heuristic_classify", END)
        return builder.compile(checkpointer=checkpointer)

    classified_targets = ["review_classification", *AGENT_NODES.values(), "unsupported_input"]
    builder.add_node("review_classification", review_classification)
    builder.add_conditional_edges("classify", after_classify,
                                  ["repair_classification", "heuristic_classify", *classified_targets])
    builder.add_conditional_edges("repair_classification", after_repair, ["heuristic_classify", *classified_targets])
    builder.add_conditional_edges("heuristic_classify", route_classified, classified_targets)
    builder.add_conditional_edges("review_classification", after_review_classification,
                                  [*AGENT_NODES.values(), "unsupported_input", END])

    # Specialised agents

    def unsupported_input(state: FlowState) -> Dict[str, Any]:
        return {"status": "error",
                "error": f"Unsupported input type: {state['classification']['input_type']}"}

    def agent_node(run: Callable[[FlowState], Dict[str, Any]]):
        def node(state: FlowState) -> Dict[str, Any]:
            output = run(state)
            if output.get("status") == "error":
                return {"agent_output": output, "status": "error",
                        "error": f"Agent processing failed: {output.get('error')}"}
            return {"agent_output": output, "status": "processed"}
        return node

    def after_agent(state: FlowState) -> str:
        return END if state.get("status") == "error" else "plan_actions"

    builder.add_node("unsupported_input", unsupported_input)
    builder.add_edge("unsupported_input", END)
    builder.add_node("email_agent", agent_node(
        lambda s: agents.email.process_email(s["content"].decode("utf-8", errors="ignore"))))
    builder.add_node("json_agent", agent_node(
        lambda s: agents.json.process_json(s["content"].decode("utf-8", errors="ignore"))))
    builder.add_node("pdf_agent", agent_node(lambda s: agents.pdf.analyze_pdf(s["content"])))
    for node in AGENT_NODES.values():
        builder.add_conditional_edges(node, after_agent, ["plan_actions", END])

    # Actions

    def plan_actions(state: FlowState) -> Dict[str, Any]:
        planned = [
            {**action, "risky": action["type"] in settings.risky_actions, "decision": None}
            for action in router.plan_actions(state["agent_output"])
        ]
        return {"planned_actions": planned, "action_index": 0, "attempt": 0, "actions_triggered": []}

    def after_plan(state: FlowState) -> str:
        planned = state["planned_actions"]
        if any(action["risky"] for action in planned):
            return "review_actions"
        return "dispatch_action" if planned else "finalize"

    def review_actions(state: FlowState) -> Dict[str, Any]:
        planned = state["planned_actions"]
        decision = dict(interrupt({
            "kind": "actions",
            "reason": "risky actions need approval",
            "actions": [{"type": a["type"], "payload": a["payload"]} for a in planned if a["risky"]]
        }) or {})
        verdict = "approved" if decision.get("approved") is True else "rejected"
        return {
            "reviews": state.get("reviews", []) + [{"kind": "actions", **decision}],
            "planned_actions": [{**a, "decision": verdict} if a["risky"] else a for a in planned]
        }

    def dispatch_action(state: FlowState) -> Dict[str, Any]:
        index, attempt = state["action_index"], state.get("attempt", 0)
        action = state["planned_actions"][index]
        done = list(state.get("actions_triggered", []))

        if action["decision"] == "rejected":
            done.append({"action": action["type"], "status": "skipped", "reason": "rejected in review"})
            return {"actions_triggered": done, "action_index": index + 1, "attempt": 0}

        if attempt:
            sleep(settings.retry_base_delay * 2 ** (attempt - 1))
        try:
            response = router.send(action["type"], action["payload"])
        except (httpx.HTTPError, ValueError) as e:
            if attempt < settings.max_retries:
                logger.warning(f"Action {action['type']} failed ({e}), retry {attempt + 1}/{settings.max_retries}")
                # Same index, one more attempt: the edge loops back to this node
                return {"attempt": attempt + 1}
            logger.warning(f"Action {action['type']} failed after {settings.max_retries} retries, using mock response")
            response = router.mock_response(action["type"], action["payload"])

        done.append({"action": action["type"], "attempts": attempt + 1, "response": response})
        return {"actions_triggered": done, "action_index": index + 1, "attempt": 0}

    def after_dispatch(state: FlowState) -> str:
        if state["action_index"] < len(state["planned_actions"]):
            return "dispatch_action"
        return "finalize"

    def finalize(state: FlowState) -> Dict[str, Any]:
        return {"status": "completed"}

    builder.add_node("plan_actions", plan_actions)
    builder.add_node("review_actions", review_actions)
    builder.add_node("dispatch_action", dispatch_action)
    builder.add_node("finalize", finalize)
    builder.add_conditional_edges("plan_actions", after_plan, ["review_actions", "dispatch_action", "finalize"])
    builder.add_edge("review_actions", "dispatch_action")
    builder.add_conditional_edges("dispatch_action", after_dispatch, ["dispatch_action", "finalize"])
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)
