from typing import Dict, Any, List, Optional
import httpx
import json
import os
import asyncio
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
    """Routes actions based on agent outputs and triggers appropriate endpoints"""
    
    def __init__(self, client: Optional[httpx.AsyncClient] = None, base_delay: float = 1.0,
                 sync_client: Optional[httpx.Client] = None):
        self.endpoints = {
            "crm": os.getenv("CRM_ENDPOINT", "http://localhost:8001/crm"),
            "risk_alert": os.getenv("RISK_ALERT_ENDPOINT", "http://localhost:8002/risk"),
            "compliance": os.getenv("COMPLIANCE_ENDPOINT", "http://localhost:8003/compliance"),
            "notification": os.getenv("NOTIFICATION_ENDPOINT", "http://localhost:8004/notify")
        }
        self.client = client or httpx.AsyncClient(timeout=30.0)
        self.max_retries = 3
        self.base_delay = base_delay
        self.sync_client = sync_client or httpx.Client(timeout=30.0)

    def send(self, action_type: str, data: Dict[str, Any]) -> Any:
        """
        Make one attempt to deliver an action; retries are the caller's job

        Raises:
            httpx.HTTPError: endpoint unreachable or returned an error status
            ValueError: unknown action type or a non-JSON reply
        """
        if action_type not in self.endpoints:
            raise ValueError(f"Unknown action type: {action_type}")
        response = self.sync_client.post(self.endpoints[action_type], json=data)
        response.raise_for_status()
        return response.json()

    async def route_action(self, action_type: str, data: Dict[str, Any], retries: int = 0) -> Dict[str, Any]:
        """
        Route an action to the appropriate endpoint with retry logic
        
        Args:
            action_type: Type of action to route (crm, risk_alert, etc.)
            data: Data to send with the action
            retries: Current retry count
            
        Returns:
            dict: Response from the endpoint
        """
        if action_type not in self.endpoints:
            raise ValueError(f"Unknown action type: {action_type}")

        endpoint = self.endpoints[action_type]
        
        try:
            response = await self.client.post(
                endpoint,
                json=data,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as e:
            if retries < self.max_retries:
                # Exponential backoff: wait base_delay * 2^retries seconds
                wait_time = self.base_delay * 2 ** retries
                logger.warning(f"Action {action_type} failed, retrying in {wait_time}s (attempt {retries + 1}/{self.max_retries})")
                await asyncio.sleep(wait_time)
                return await self.route_action(action_type, data, retries + 1)
            else:
                logger.warning(f"Action {action_type} failed after {self.max_retries} retries, using mock response")
                # Return mock response when external service is unavailable
                return self.mock_response(action_type, data)

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

    async def process_agent_output(self, agent_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process agent output and trigger appropriate actions
        
        Args:
            agent_output: Output from any of the agents
            
        Returns:
            list: Results of triggered actions
        """
        actions = []
        
        try:
            for action in self.plan_actions(agent_output):
                actions.append(await self.route_action(action["type"], action["payload"]))
        except Exception as e:
            logger.error(f"Error processing agent output: {str(e)}")
            actions.append({
                "status": "error",
                "error": f"Failed to process agent output: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            })
            
        return actions

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

# Initialize action router
action_router = ActionRouter() 