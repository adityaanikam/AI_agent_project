from typing import Dict, Any, Optional
import io
from pypdf import PdfReader
import re
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm import get_chat_model, structured_call_with_repair
from app.schemas import PDFAnalysis

PDF_SYSTEM_PROMPT = """You are a PDF analysis expert. Your task is to:
1. Extract key information from the document
2. Identify document type (invoice, contract, report, policy, other)
3. Extract line items and totals
4. Check for compliance keywords and judge the risk level (high, medium, low)

Respond with JSON matching the provided schema."""

class PDFAgent:
    """Agent responsible for processing PDF documents"""
    
    def __init__(self, llm: Optional[BaseChatModel] = None):
        self._llm = llm
        
        # Compliance keywords to check for
        self.compliance_keywords = {
            "GDPR": ["gdpr", "data protection", "privacy"],
            "FDA": ["fda", "food and drug", "medical device"],
            "HIPAA": ["hipaa", "health insurance", "protected health"],
            "PCI": ["pci", "payment card", "credit card"],
            "SOX": ["sox", "sarbanes-oxley", "financial control"]
        }

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = get_chat_model()
        return self._llm

    def analyze_pdf(self, pdf_content: bytes) -> Dict[str, Any]:
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
            
            # Analyze with the model, one repair on a parse failure
            result = structured_call_with_repair(self.llm, PDFAnalysis, [
                SystemMessage(content=PDF_SYSTEM_PROMPT),
                HumanMessage(content=f"PDF content to analyze:\n{text_content[:1000]}")
            ])
            if result.ok:
                analysis = result.parsed.model_dump(mode="json")
            else:
                # Fallback analysis if the model gave no valid answer
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
                "analysis_source": "llm" if result.ok else "fallback",
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