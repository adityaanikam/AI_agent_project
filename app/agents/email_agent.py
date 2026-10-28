from typing import Dict, Any, Optional
from email.parser import Parser
from email.policy import default
import re
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm import get_chat_model, structured_call_with_repair
from app.schemas import EmailAnalysis

EMAIL_SYSTEM_PROMPT = """You are an email analysis expert. Your task is to:
1. Analyze the email content
2. Determine the tone (formal, informal, urgent, neutral)
3. Identify key entities: people, organizations, dates, amounts
4. Extract actionable items
5. Assess urgency level (high, medium, low)
6. Judge sentiment (positive, negative, neutral) and list key topics

Respond with JSON matching the provided schema."""

class EmailAgent:
    """Agent responsible for processing email content"""
    
    def __init__(self, llm: Optional[BaseChatModel] = None):
        self._llm = llm

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = get_chat_model()
        return self._llm

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
                "has_attachments": any(True for _ in email.iter_attachments())
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
            
            # Analyze content with the model, one repair on a parse failure
            result = structured_call_with_repair(self.llm, EmailAnalysis, [
                SystemMessage(content=EMAIL_SYSTEM_PROMPT),
                HumanMessage(content=f"Email content to analyze:\n{body[:1000]}")
            ])
            if result.ok:
                analysis = result.parsed.model_dump(mode="json")
            else:
                # Fallback analysis if the model gave no valid answer
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
                "analysis_source": "llm" if result.ok else "fallback",
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