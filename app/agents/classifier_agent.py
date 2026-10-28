from typing import Dict, Any, List, Optional
import json
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.llm import StructuredResult, get_chat_model, repair_messages, structured_call
from app.schemas import Classification

# Confidence reported by the keyword heuristic, which is a guess
HEURISTIC_CONFIDENCE = 0.5

CLASSIFIER_SYSTEM_PROMPT = """You classify incoming business content. Respond with JSON matching the provided schema.

input_type: "json" for JSON payloads, "email" for email messages, "pdf" for PDF documents.

business_intent must NEVER be null. Always assign one of these values:
- "Invoice" (for bills, payments, receipts, financial documents)
- "Complaint" (for urgent issues, problems, errors, outages)
- "RFQ" (for quotes, requests, proposals, bids)
- "Regulation" (for compliance, legal, policy, GDPR, audit documents)
- "Fraud Risk" (for security alerts, suspicious activity)
- "Certificate" (for completion certificates, diplomas, achievements)
- "Report" (for analysis, summaries, findings)
- "General" (for any other content)

confidence: a number from 0.0 to 1.0.
metadata.urgency: "high", "medium" or "low"."""


class ClassifierAgent:
    """Agent responsible for classifying input type and business intent"""

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self._llm = llm

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = get_chat_model()
        return self._llm

    def messages(self, content: str) -> List[BaseMessage]:
        """Prompt sent to the model for `content`"""
        return [
            SystemMessage(content=CLASSIFIER_SYSTEM_PROMPT),
            HumanMessage(content=f"Content to classify: {content[:800]}")
        ]

    def llm_classify(self, content: str) -> StructuredResult:
        """Ask the model for a Classification"""
        return structured_call(self.llm, Classification, self.messages(content))

    def repair(self, content: str, failed: StructuredResult) -> StructuredResult:
        """Re-ask the model with its invalid reply and the validation error"""
        return structured_call(self.llm, Classification, repair_messages(self.messages(content), failed))

    def heuristic(self, content: str) -> Dict[str, Any]:
        """Keyword-based classification used when the model gives no valid answer"""
        input_type = self._detect_input_type(content)
        return {
            "input_type": input_type,
            "business_intent": self._detect_intent(content),
            "confidence": HEURISTIC_CONFIDENCE,
            "metadata": self._extract_metadata(content, input_type)
        }

    def _detect_input_type(self, content: str) -> str:
        """Fallback method to detect input type"""
        content_lower = content.lower()
        content_strip = content.strip()

        if content_strip.startswith('{') and content_strip.endswith('}'):
            return "json"
        elif "from:" in content_lower and ("to:" in content_lower or "subject:" in content_lower):
            return "email"
        elif content.startswith('%PDF'):
            return "pdf"
        elif "event_type" in content_lower or "webhook" in content_lower:
            return "json"
        elif "dear" in content_lower or "regards" in content_lower:
            return "email"
        else:
            return "unknown"

    def _detect_intent(self, content: str) -> str:
        """Detect business intent using keywords"""
        content_lower = content.lower()

        # Check for complaint/urgent keywords first (highest priority)
        if any(keyword in content_lower for keyword in ["urgent", "critical", "outage", "down", "error", "complaint", "issue", "problem"]):
            return "Complaint"

        # Check for invoice keywords
        if any(keyword in content_lower for keyword in ["invoice", "payment", "bill", "amount", "total", "due", "remittance", "receipt"]):
            return "Invoice"

        # Check for RFQ keywords
        if any(keyword in content_lower for keyword in ["quote", "rfq", "request", "proposal", "bid", "tender", "quotation"]):
            return "RFQ"

        # Check for regulation/compliance keywords
        if any(keyword in content_lower for keyword in ["gdpr", "compliance", "regulation", "audit", "policy", "legal", "regulatory"]):
            return "Regulation"

        # Check for fraud/risk keywords
        if any(keyword in content_lower for keyword in ["fraud", "suspicious", "risk", "alert", "security", "unauthorized"]):
            return "Fraud Risk"

        # Check for certificate/completion documents
        if any(keyword in content_lower for keyword in ["certificate", "completion", "certification", "diploma", "achievement"]):
            return "Certificate"

        # Check for report keywords
        if any(keyword in content_lower for keyword in ["report", "analysis", "summary", "findings", "results"]):
            return "Report"

        # Default fallback - never return empty
        return "General"

    def _extract_metadata(self, content: str, input_type: str) -> Dict[str, Any]:
        """
        Extract metadata based on input type

        Args:
            content: The content to analyze
            input_type: The type of input (email, json, pdf)

        Returns:
            dict: Extracted metadata
        """
        metadata = {}
        content_lower = content.lower()

        if input_type == "email":
            # Extract email-specific metadata
            metadata.update({
                "has_attachments": "attachment" in content_lower,
                "is_reply": content_lower.startswith("re:"),
                "is_forward": content_lower.startswith("fw:"),
                "urgency": "high" if any(word in content_lower for word in ["urgent", "critical", "asap"]) else "medium"
            })
        elif input_type == "json":
            # Extract JSON-specific metadata
            try:
                data = json.loads(content)
                if not isinstance(data, dict):
                    data = {}
                metadata.update({
                    "has_nested_objects": any(isinstance(v, dict) for v in data.values()),
                    "field_count": len(data),
                    "amount": data.get("amount") or (data.get("data", {}).get("amount") if isinstance(data.get("data"), dict) else None)
                })
            except json.JSONDecodeError:
                metadata.update({
                    "has_nested_objects": False,
                    "field_count": 0
                })
        elif input_type == "pdf":
            # Extract PDF-specific metadata
            metadata.update({
                "has_tables": "table" in content_lower,
                "has_images": "image" in content_lower,
                "document_type": "invoice" if "invoice" in content_lower else "other"
            })

        return metadata

# Initialize classifier agent
classifier_agent = ClassifierAgent()
