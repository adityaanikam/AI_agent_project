#!/usr/bin/env python3
"""
Debug classifier responses
"""
import asyncio
import os
import json
import re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate

# Load environment variables
load_dotenv()

model = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.1,
    convert_system_message_to_human=True
)

classification_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a classification expert. Your task is to:
1. Determine the input format (email, json, pdf)
2. Identify the business intent (RFQ, Complaint, Invoice, Regulation, Fraud Risk)
3. Extract key metadata

IMPORTANT: Return ONLY a valid JSON object, no other text or formatting.

Provide your response in this exact JSON format:
{
    "input_type": "email",
    "business_intent": "Complaint",
    "confidence": 0.9,
    "metadata": {
        "urgency": "high",
        "contains_keywords": ["urgent", "outage"]
    }
}"""),
    ("human", "{input}")
])

async def test_classification():
    """Test classification with sample data"""
    
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
    
    try:
        messages = classification_prompt.format_messages(input=json_content)
        response = await model.ainvoke(messages)
        
        print(f"\nRaw response: '{response.content}'")
        print(f"Response type: {type(response.content)}")
        print(f"Response length: {len(response.content)}")
        
        # Print character codes for first 50 characters
        print(f"\nFirst 50 characters as ASCII codes:")
        for i, char in enumerate(response.content[:50]):
            print(f"{i}: '{char}' (ASCII: {ord(char)})")
        
        # Try to clean and parse
        content_str = response.content.strip()
        print(f"\nAfter strip: '{content_str}'")
        
        # Remove markdown formatting
        content_str = re.sub(r'```json\s*', '', content_str)
        content_str = re.sub(r'```\s*$', '', content_str)
        content_str = content_str.strip()
        print(f"After markdown removal: '{content_str}'")
        
        # Find JSON content
        if '{' in content_str and '}' in content_str:
            start = content_str.find('{')
            end = content_str.rfind('}') + 1
            json_str = content_str[start:end]
            print(f"Extracted JSON: '{json_str}'")
            
            # Clean escape characters
            json_str = json_str.replace('\\n', ' ').replace('\\t', ' ')
            json_str = re.sub(r'\s+', ' ', json_str)
            print(f"Cleaned JSON: '{json_str}'")
            
            try:
                parsed = json.loads(json_str)
                print(f"✅ Successfully parsed: {parsed}")
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing failed: {e}")
                print(f"Character at error position: '{json_str[e.pos] if e.pos < len(json_str) else 'EOF'}'")
        else:
            print("❌ No JSON braces found")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_classification()) 