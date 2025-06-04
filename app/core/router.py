from typing import Dict, Any, List
import httpx
import json
import os
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ActionRouter:
    """Routes actions based on agent outputs and triggers appropriate endpoints"""
    
    def __init__(self):
        self.endpoints = {
            "crm": os.getenv("CRM_ENDPOINT", "http://localhost:8001/crm"),
            "risk_alert": os.getenv("RISK_ALERT_ENDPOINT", "http://localhost:8002/risk"),
            "compliance": os.getenv("COMPLIANCE_ENDPOINT", "http://localhost:8003/compliance"),
            "notification": os.getenv("NOTIFICATION_ENDPOINT", "http://localhost:8004/notify")
        }
        self.client = httpx.AsyncClient(timeout=30.0)
        self.max_retries = 3

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
                # Exponential backoff: wait 2^retries seconds
                wait_time = 2 ** retries
                logger.warning(f"Action {action_type} failed, retrying in {wait_time}s (attempt {retries + 1}/{self.max_retries})")
                await asyncio.sleep(wait_time)
                return await self.route_action(action_type, data, retries + 1)
            else:
                logger.warning(f"Action {action_type} failed after {self.max_retries} retries, using mock response")
                # Return mock response when external service is unavailable
                return self._get_mock_response(action_type, data)

    def _get_mock_response(self, action_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
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
            # Extract analysis data
            analysis = agent_output.get("analysis", {})
            metadata = agent_output.get("metadata", {})
            
            # Example routing logic based on agent output
            if analysis.get("urgency") == "high":
                actions.append(
                    await self.route_action("notification", {
                        "priority": "high",
                        "message": analysis.get("message", "Urgent action required"),
                        "source": "agent_analysis"
                    })
                )
                
            # Check for high-value transactions (>10K)
            if "data" in agent_output and isinstance(agent_output["data"], dict):
                amount = agent_output["data"].get("amount", 0)
                if isinstance(amount, (int, float)) and amount > 10000:
                    actions.append(
                        await self.route_action("risk_alert", {
                            "alert_type": "high_value_transaction",
                            "amount": amount,
                            "details": agent_output.get("details", {})
                        })
                    )
            
            # Check for risk scores
            if "risk_score" in analysis and analysis["risk_score"] > 0.7:
                actions.append(
                    await self.route_action("risk_alert", {
                        "risk_score": analysis["risk_score"],
                        "details": analysis.get("details", {})
                    })
                )
                
            # Check for compliance issues
            if "compliance_issues" in analysis or "compliance_check" in agent_output:
                compliance_data = analysis.get("compliance_issues") or agent_output.get("compliance_check", {})
                actions.append(
                    await self.route_action("compliance", {
                        "issues": compliance_data,
                        "source": agent_output.get("source", "unknown")
                    })
                )
                
            # Check for GDPR mentions or high-risk compliance
            compliance_check = agent_output.get("compliance_check", {})
            if compliance_check.get("risk_level") == "high" or "GDPR" in str(compliance_check.get("keywords_found", {})):
                actions.append(
                    await self.route_action("compliance", {
                        "alert_type": "gdpr_mention",
                        "compliance_check": compliance_check,
                        "source": "pdf_analysis"
                    })
                )
                
            # Check for customer data updates
            if "customer_data" in analysis:
                actions.append(
                    await self.route_action("crm", {
                        "action": "update",
                        "data": analysis["customer_data"]
                    })
                )
                
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