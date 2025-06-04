#!/usr/bin/env python3
"""
Test classifier directly
"""
from app.agents.classifier_agent import classifier_agent

def test_classifier():
    """Test the classifier with sample data"""
    
    # Test with JSON
    json_content = """{
    "event_type": "webhook",
    "timestamp": "2024-02-20T10:00:00Z",
    "data": {
        "order_id": "12345",
        "status": "completed",
        "amount": 15000.00
    }
}"""
    
    print("=== Testing JSON Classification ===")
    print(f"Input: {json_content[:100]}...")
    
    result = classifier_agent.classify(json_content)
    print(f"Result: {result}")
    
    # Test with email
    email_content = """From: customer@example.com
To: support@company.com
Subject: URGENT: System is down

Dear Support,

Our production system has been down for 2 hours. This is critical!

Best regards,
John Doe"""

    print("\n=== Testing Email Classification ===")
    print(f"Input: {email_content[:50]}...")
    
    result = classifier_agent.classify(email_content)
    print(f"Result: {result}")

if __name__ == "__main__":
    test_classifier() 