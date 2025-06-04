from typing import Dict, Any, Tuple
import google.generativeai as genai
import os
import json
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

class ClassifierAgent:
    """Agent responsible for classifying input type and business intent"""
    
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def classify(self, content: str) -> Dict[str, Any]:
        """
        Classify the input content
        
        Args:
            content: The content to classify
            
        Returns:
            dict: Classification results
        """
        try:
            prompt = f"""Classify this content and return ONLY a JSON object with no other text.

IMPORTANT: business_intent must NEVER be null. Always assign one of these values:
- "Invoice" (for bills, payments, receipts, financial documents)
- "Complaint" (for urgent issues, problems, errors, outages) 
- "RFQ" (for quotes, requests, proposals, bids)
- "Regulation" (for compliance, legal, policy, GDPR, audit documents)
- "Fraud Risk" (for security alerts, suspicious activity)
- "Certificate" (for completion certificates, diplomas, achievements)
- "Report" (for analysis, summaries, findings)
- "General" (for any other content)

Return this exact JSON structure:
{{
    "input_type": "json|email|pdf",
    "business_intent": "one of the values above - NEVER null",
    "confidence": 0.0-1.0,
    "metadata": {{
        "urgency": "high|medium|low"
    }}
}}

Content to classify: {content[:800]}"""

            # Get classification from Gemini
            response = self.model.generate_content(prompt)
            
            # Clean and parse the response
            try:
                content_str = response.text.strip()
                print(f"Classifier raw response: '{content_str}'")
                
                # Remove markdown formatting if present
                if content_str.startswith('```'):
                    content_str = re.sub(r'```[a-z]*\s*', '', content_str)
                    content_str = re.sub(r'```\s*$', '', content_str)
                    content_str = content_str.strip()
                
                # Try to find JSON in the response
                if '{' in content_str and '}' in content_str:
                    start = content_str.find('{')
                    end = content_str.rfind('}') + 1
                    json_str = content_str[start:end]
                    
                    # Clean any problematic characters
                    json_str = json_str.replace('\n', ' ').replace('\t', ' ')
                    json_str = re.sub(r'\s+', ' ', json_str)
                    
                    classification = json.loads(json_str)
                else:
                    raise json.JSONDecodeError("No JSON found", content_str, 0)
                    
            except (json.JSONDecodeError, Exception) as e:
                print(f"JSON parsing failed: {e}")
                print(f"Failed content: '{content_str[:200]}'")
                # Fallback classification using simple heuristics
                classification = {
                    "input_type": self._detect_input_type(content),
                    "business_intent": self._detect_intent(content),
                    "confidence": 0.5,
                    "metadata": self._extract_metadata(content, self._detect_input_type(content))
                }
            
            return {
                "status": "success",
                "classification": classification
            }
        except Exception as e:
            print(f"Classification error: {e}")
            return {
                "status": "error",
                "error": str(e)
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
                metadata.update({
                    "has_nested_objects": any(isinstance(v, dict) for v in data.values()) if isinstance(data, dict) else False,
                    "field_count": len(data) if isinstance(data, dict) else 0,
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