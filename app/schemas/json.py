from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class EventType(str, Enum):
    """Enum for event types"""
    WEBHOOK = "webhook"
    API_CALL = "api_call"
    SYSTEM = "system"
    USER = "user"

class Priority(str, Enum):
    """Enum for priority levels"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class WebhookData(BaseModel):
    """Schema for webhook data"""
    event_type: EventType
    timestamp: datetime
    data: Dict[str, Any]
    source: str
    version: str = "1.0"
    signature: Optional[str] = None

class APIResponse(BaseModel):
    """Schema for API responses"""
    status: str = Field(..., pattern="^(success|error)$")
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime
    request_id: str

class SystemEvent(BaseModel):
    """Schema for system events"""
    event_type: str
    severity: str = Field(..., pattern="^(critical|error|warning|info)$")
    message: str
    timestamp: datetime
    component: str
    details: Optional[Dict[str, Any]] = None

class UserAction(BaseModel):
    """Schema for user actions"""
    user_id: str
    action: str
    timestamp: datetime
    resource: str
    metadata: Optional[Dict[str, Any]] = None

# Sample JSON formats
SAMPLE_WEBHOOK = {
    "event_type": "webhook",
    "timestamp": "2024-02-20T10:00:00Z",
    "data": {
        "order_id": "12345",
        "status": "completed",
        "amount": 99.99
    },
    "source": "payment_gateway",
    "version": "1.0",
    "signature": "abc123..."
}

SAMPLE_API_RESPONSE = {
    "status": "success",
    "data": {
        "user": {
            "id": "123",
            "name": "John Doe",
            "email": "john@example.com"
        }
    },
    "timestamp": "2024-02-20T10:00:00Z",
    "request_id": "req_123456"
}

SAMPLE_SYSTEM_EVENT = {
    "event_type": "database_error",
    "severity": "error",
    "message": "Failed to connect to database",
    "timestamp": "2024-02-20T10:00:00Z",
    "component": "database",
    "details": {
        "error_code": "DB_CONN_001",
        "attempt": 3
    }
}

SAMPLE_USER_ACTION = {
    "user_id": "user_123",
    "action": "login",
    "timestamp": "2024-02-20T10:00:00Z",
    "resource": "auth",
    "metadata": {
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0..."
    }
} 