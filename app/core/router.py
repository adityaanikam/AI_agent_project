from typing import Dict, Any, List, Optional
import httpx
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

HIGH_VALUE_THRESHOLD = 10000


def _find_amount(parsed_data: Any) -> Optional[float]:
    """Return the transaction amount from a parsed JSON payload, if any"""
    if not isinstance(parsed_data, dict):
        return None
    candidates = [parsed_data.get("amount")]
    if isinstance(parsed_data.get("data"), dict):
        candidates.append(parsed_data["data"].get("amount"))
    for value in candidates:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None

class ActionRouter:
    """Decides which actions an agent output triggers and delivers them to their endpoints"""
    
    def __init__(self, client: Optional[httpx.Client] = None):
        self.endpoints = {
            "crm": os.getenv("CRM_ENDPOINT", "http://localhost:8001/crm"),
            "risk_alert": os.getenv("RISK_ALERT_ENDPOINT", "http://localhost:8002/risk"),
            "compliance": os.getenv("COMPLIANCE_ENDPOINT", "http://localhost:8003/compliance"),
            "notification": os.getenv("NOTIFICATION_ENDPOINT", "http://localhost:8004/notify")
        }
        self.client = client or httpx.Client(timeout=30.0)

    def send(self, action_type: str, data: Dict[str, Any]) -> Any:
        """
        Make one attempt to deliver an action; retries are the caller's job

        Raises:
            httpx.HTTPError: endpoint unreachable or returned an error status
            ValueError: unknown action type or a non-JSON reply
        """
        if action_type not in self.endpoints:
            raise ValueError(f"Unknown action type: {action_type}")
        response = self.client.post(self.endpoints[action_type], json=data)
        response.raise_for_status()
        return response.json()

    def mock_response(self, action_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate mock responses for when external services are unavailable"""
        base_response = {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "mock": True,
            "message": f"Mock response for {action_type} service"
        }
        
        if action_type == "notification":
            return {
                **base_response,
                "notification_id": f"mock_notif_{datetime.utcnow().timestamp()}",
                "priority": data.get("priority", "medium"),
                "message": "Notification sent successfully (mock)"
            }
        elif action_type == "risk_alert":
            return {
                **base_response,
                "alert_id": f"mock_alert_{datetime.utcnow().timestamp()}",
                "risk_level": "assessed",
                "message": "Risk alert processed successfully (mock)"
            }
        elif action_type == "compliance":
            return {
                **base_response,
                "compliance_id": f"mock_comp_{datetime.utcnow().timestamp()}",
                "review_status": "scheduled",
                "message": "Compliance review initiated successfully (mock)"
            }
        elif action_type == "crm":
            return {
                **base_response,
                "record_id": f"mock_crm_{datetime.utcnow().timestamp()}",
                "action": data.get("action", "update"),
                "message": "CRM update processed successfully (mock)"
            }
        else:
            return {
                **base_response,
                "message": f"Mock response for unknown action type: {action_type}"
            }

    def plan_actions(self, agent_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Decide which actions an agent output should trigger.

        Only reads fields the agents actually produce:
        - email agent: analysis.urgency, metadata.subject
        - JSON agent: parsed_data (amount at top level or under "data")
        - PDF agent: compliance_check.keywords_found / risk_level

        Returns:
            list: [{"type": <endpoint name>, "payload": {...}}]
        """
        planned = []
        analysis = agent_output.get("analysis") or {}
        metadata = agent_output.get("metadata") or {}

        if analysis.get("urgency") == "high":
            planned.append({"type": "notification", "payload": {
                "priority": "high",
                "message": metadata.get("subject") or "Urgent action required",
                "source": "agent_analysis"
            }})

        # High-value transactions (>10K) in JSON payloads
        amount = _find_amount(agent_output.get("parsed_data"))
        if amount is not None and amount > HIGH_VALUE_THRESHOLD:
            planned.append({"type": "risk_alert", "payload": {
                "alert_type": "high_value_transaction",
                "amount": amount
            }})

        # One compliance action per document, only when keywords were found
        compliance_check = agent_output.get("compliance_check") or {}
        keywords_found = compliance_check.get("keywords_found") or {}
        if keywords_found:
            is_gdpr = "GDPR" in keywords_found or compliance_check.get("risk_level") == "high"
            planned.append({"type": "compliance", "payload": {
                "alert_type": "gdpr_mention" if is_gdpr else "compliance_keywords",
                "compliance_check": compliance_check,
                "source": "pdf_analysis"
            }})

        return planned

    def close(self):
        """Close the HTTP client"""
        self.client.close()
