from typing import Any, Dict, List, TypedDict


class FlowState(TypedDict, total=False):
    """State carried through the processing graph and saved at every step"""

    # Input
    process_id: str
    filename: str
    content: bytes

    # Classification
    text: str                      # decoded content given to the classifier
    classification: Dict[str, Any]
    classification_source: str     # llm | repair | heuristic | review
    llm_reply: Dict[str, Any]      # last invalid model reply, input to the repair node

    # Specialised agent
    agent_output: Dict[str, Any]

    # Actions
    planned_actions: List[Dict[str, Any]]  # {"type", "payload", "risky", "decision"}
    action_index: int              # next planned action to dispatch
    attempt: int                   # failed attempts so far for that action
    actions_triggered: List[Dict[str, Any]]

    # Human review: the decisions given when the run was resumed
    reviews: List[Dict[str, Any]]

    status: str
    error: str
