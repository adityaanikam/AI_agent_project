from typing import Dict, Any, List
import google.generativeai as genai
import os
import json
import io
from pypdf import PdfReader
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

class PDFAgent:
    """Agent responsible for processing PDF documents"""
    
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Compliance keywords to check for
        self.compliance_keywords = {
            "GDPR": ["gdpr", "data protection", "privacy"],
            "FDA": ["fda", "food and drug", "medical device"],
            "HIPAA": ["hipaa", "health insurance", "protected health"],
            "PCI": ["pci", "payment card", "credit card"],
            "SOX": ["sox", "sarbanes-oxley", "financial control"]
        }

    async def process_pdf(self, pdf_content: bytes) -> Dict[str, Any]:
        """
        Process PDF content
        
        Args:
            pdf_content: Raw PDF content as bytes
            
        Returns:
            dict: Analysis results
        """
        try:
            # Parse PDF from bytes
            pdf_stream = io.BytesIO(pdf_content)
            pdf = PdfReader(pdf_stream)
            
            # Extract text from all pages
            text_content = ""
            for page in pdf.pages:
                text_content += page.extract_text()
            
            # Analyze with Gemini
            prompt = f"""You are a PDF analysis expert. Your task is to:
1. Extract key information from the document
2. Identify document type (invoice, contract, report, etc.)
3. Extract line items and totals
4. Check for compliance keywords
5. Assess document completeness

Provide your response in JSON format with the following structure:
{{
    "document_type": "invoice|contract|report|other",
    "line_items": [
        {{
            "description": "string",
            "amount": 0.0,
            "quantity": 1
        }}
    ],
    "totals": {{
        "subtotal": 0.0,
        "tax": 0.0,
        "total": 0.0
    }},
    "compliance": {{
        "keywords_found": [],
        "risk_level": "high|medium|low"
    }},
    "metadata": {{
        "page_count": 1,
        "has_tables": false,
        "has_signatures": false
    }}
}}

PDF content to analyze:
{text_content[:1000]}"""

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
                    "document_type": "other",
                    "line_items": [],
                    "totals": {
                        "subtotal": 0.0,
                        "tax": 0.0,
                        "total": 0.0
                    },
                    "compliance": {
                        "keywords_found": [],
                        "risk_level": "low"
                    },
                    "metadata": {
                        "page_count": len(pdf.pages),
                        "has_tables": self._detect_tables(text_content),
                        "has_signatures": self._detect_signatures(text_content)
                    }
                }
            
            # Check for compliance keywords
            compliance_check = self._check_compliance(text_content)
            
            # Extract metadata
            metadata = {
                "page_count": len(pdf.pages),
                "has_tables": self._detect_tables(text_content),
                "has_signatures": self._detect_signatures(text_content)
            }
            
            return {
                "status": "success",
                "analysis": analysis,
                "compliance_check": compliance_check,
                "metadata": metadata,
                "raw_text": text_content
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def _check_compliance(self, text: str) -> Dict[str, Any]:
        """Check for compliance keywords in text"""
        found_keywords = {}
        text_lower = text.lower()
        
        for category, keywords in self.compliance_keywords.items():
            found = [k for k in keywords if k in text_lower]
            if found:
                found_keywords[category] = found
                
        return {
            "keywords_found": found_keywords,
            "risk_level": "high" if len(found_keywords) > 2 else "medium" if found_keywords else "low"
        }

    def _detect_tables(self, text: str) -> bool:
        """Detect if text contains table-like structures"""
        # Look for patterns that might indicate tables
        table_patterns = [
            r'\|\s*[^\n]+\s*\|',  # Pipe-separated tables
            r'\+[-+]+\+',         # ASCII tables
            r'\t[^\n]+\t'         # Tab-separated content
        ]
        
        return any(re.search(pattern, text) for pattern in table_patterns)

    def _detect_signatures(self, text: str) -> bool:
        """Detect if text contains signature-like content"""
        signature_patterns = [
            r'(?i)signed by:',
            r'(?i)signature:',
            r'(?i)authorized by:',
            r'(?i)approved by:'
        ]
        
        return any(re.search(pattern, text) for pattern in signature_patterns)

# Initialize PDF agent
pdf_agent = PDFAgent() 