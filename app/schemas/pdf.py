from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class DocumentType(str, Enum):
    """Enum for document types"""
    INVOICE = "invoice"
    CONTRACT = "contract"
    REPORT = "report"
    POLICY = "policy"
    OTHER = "other"

class RiskLevel(str, Enum):
    """Enum for risk levels"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class LineItem(BaseModel):
    """Schema for line items in documents"""
    description: str
    amount: float
    quantity: Optional[int] = 1
    unit_price: Optional[float] = None
    tax_rate: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

class DocumentTotals(BaseModel):
    """Schema for document totals"""
    subtotal: float
    tax: Optional[float] = 0.0
    total: float
    currency: str = "USD"
    exchange_rate: Optional[float] = None

class ComplianceCheck(BaseModel):
    """Schema for compliance check results"""
    keywords_found: Dict[str, List[str]]
    risk_level: RiskLevel
    regulations: List[str]
    recommendations: Optional[List[str]] = None

class DocumentMetadata(BaseModel):
    """Schema for document metadata"""
    page_count: int
    has_tables: bool
    has_signatures: bool
    has_images: bool
    created_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None
    author: Optional[str] = None
    title: Optional[str] = None

class PDFDocument(BaseModel):
    """Complete PDF document schema"""
    document_type: DocumentType
    line_items: Optional[List[LineItem]] = None
    totals: Optional[DocumentTotals] = None
    compliance: Optional[ComplianceCheck] = None
    metadata: DocumentMetadata
    raw_text: str

# Sample PDF formats
SAMPLE_INVOICE = {
    "document_type": "invoice",
    "line_items": [
        {
            "description": "Software License",
            "amount": 999.99,
            "quantity": 1,
            "unit_price": 999.99,
            "tax_rate": 0.1
        },
        {
            "description": "Support Package",
            "amount": 199.99,
            "quantity": 1,
            "unit_price": 199.99,
            "tax_rate": 0.1
        }
    ],
    "totals": {
        "subtotal": 1199.98,
        "tax": 119.99,
        "total": 1319.97,
        "currency": "USD"
    },
    "metadata": {
        "page_count": 1,
        "has_tables": True,
        "has_signatures": True,
        "has_images": False,
        "created_date": "2024-02-20T10:00:00Z"
    }
}

SAMPLE_CONTRACT = {
    "document_type": "contract",
    "compliance": {
        "keywords_found": {
            "GDPR": ["data protection", "privacy"],
            "PCI": ["payment card", "credit card"]
        },
        "risk_level": "high",
        "regulations": ["GDPR", "PCI-DSS"],
        "recommendations": [
            "Review data handling procedures",
            "Update security measures"
        ]
    },
    "metadata": {
        "page_count": 5,
        "has_tables": True,
        "has_signatures": True,
        "has_images": False,
        "created_date": "2024-02-20T10:00:00Z",
        "author": "Legal Department"
    }
}

SAMPLE_REPORT = {
    "document_type": "report",
    "metadata": {
        "page_count": 10,
        "has_tables": True,
        "has_signatures": False,
        "has_images": True,
        "created_date": "2024-02-20T10:00:00Z",
        "title": "Q1 Financial Report"
    }
} 