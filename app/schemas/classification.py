from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

InputType = Literal["email", "json", "pdf"]

BusinessIntent = Literal[
    "Invoice",
    "Complaint",
    "RFQ",
    "Regulation",
    "Fraud Risk",
    "Certificate",
    "Report",
    "General"
]

class ClassificationMetadata(BaseModel):
    """Metadata attached to a classification; the heuristic fallback adds more keys"""
    model_config = ConfigDict(extra="allow")

    urgency: Literal["high", "medium", "low"] = "medium"

class Classification(BaseModel):
    """Classifier output: input format, business intent and confidence"""
    input_type: InputType
    business_intent: BusinessIntent
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata: ClassificationMetadata = Field(default_factory=ClassificationMetadata)
