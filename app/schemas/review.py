from pydantic import BaseModel
from typing import Optional

from .classification import BusinessIntent, InputType

class ReviewDecision(BaseModel):
    """Reviewer's answer to a paused run, sent to POST /review/{process_id}"""
    approved: bool
    # Classification reviews only: correct the classifier before the agent runs
    input_type: Optional[InputType] = None
    business_intent: Optional[BusinessIntent] = None
    note: Optional[str] = None
