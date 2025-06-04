from typing import Dict, Any
import google.generativeai as genai
import json
import os
from email.parser import Parser
from email.policy import default
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

class EmailAgent:
    """Agent responsible for processing email content"""
    
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def process_email(self, email_content: str) -> Dict[str, Any]:
        """
        Process email content
        
        Args:
            email_content: Raw email content
            
        Returns:
            dict: Analysis results
        """
        try:
            # Parse email
            email = Parser(policy=default).parsestr(email_content)
            
            # Extract basic metadata
            metadata = {
                "from": email.get("from", ""),
                "to": email.get("to", ""),
                "subject": email.get("subject", ""),
                "date": email.get("date", ""),
                "has_attachments": bool(email.get_payload() and len(email.get_payload()) > 1)
            }
            
            # Get email body
            body = ""
            if email.is_multipart():
                for part in email.get_payload():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode()
                        break
            else:
                body = email.get_payload(decode=True).decode()
            
            # Analyze content with Gemini
            prompt = f"""You are an email analysis expert. Your task is to:
1. Analyze the email content
2. Determine the tone (formal, informal, urgent, etc.)
3. Identify key entities and relationships
4. Extract actionable items
5. Assess urgency level

Provide your response in JSON format with the following structure:
{{
    "tone": "formal|informal|urgent|neutral",
    "urgency": "high|medium|low",
    "entities": {{
        "people": [],
        "organizations": [],
        "dates": [],
        "amounts": []
    }},
    "action_items": [],
    "sentiment": "positive|negative|neutral",
    "key_topics": []
}}

Email content to analyze:
{body[:1000]}"""

            response = self.model.generate_content(prompt)
            
            # Parse the response safely
            try:
                content_str = response.text.strip()
                # Find JSON content between curly braces
                if '{' in content_str and '}' in content_str:
                    start = content_str.find('{')
                    end = content_str.rfind('}') + 1
                    json_str = content_str[start:end]
                    analysis = json.loads(json_str)
                else:
                    analysis = json.loads(content_str)
            except json.JSONDecodeError:
                # Fallback analysis if parsing fails
                analysis = {
                    "tone": "neutral",
                    "urgency": "medium",
                    "entities": self._extract_entities(body),
                    "action_items": [],
                    "sentiment": "neutral",
                    "key_topics": []
                }
            
            # Combine results
            return {
                "status": "success",
                "metadata": metadata,
                "analysis": analysis,
                "raw_content": body
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def _extract_entities(self, text: str) -> Dict[str, list]:
        """Extract named entities from text"""
        # This is a placeholder - in production, you'd use a proper NER model
        entities = {
            "people": [],
            "organizations": [],
            "dates": [],
            "amounts": []
        }
        
        # Simple regex patterns for demonstration
        entities["dates"] = re.findall(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', text)
        entities["amounts"] = re.findall(r'\$\d+(?:,\d{3})*(?:\.\d{2})?', text)
        
        return entities

# Initialize email agent
email_agent = EmailAgent() 