"""
Data models and validation schemas
"""

from .classification import (
    Classification,
    ClassificationMetadata
)

from .review import ReviewDecision

from .email import (
    EmailDocument,
    EmailMetadata,
    EmailContent,
    EmailAnalysis,
    EmailAttachment,
    SAMPLE_EMAIL
)

from .json import (
    WebhookData,
    APIResponse,
    SystemEvent,
    UserAction,
    JSONAnalysis,
    SAMPLE_WEBHOOK,
    SAMPLE_API_RESPONSE,
    SAMPLE_SYSTEM_EVENT,
    SAMPLE_USER_ACTION
)

from .pdf import (
    PDFDocument,
    LineItem,
    DocumentTotals,
    ComplianceCheck,
    DocumentMetadata,
    PDFAnalysis,
    SAMPLE_INVOICE,
    SAMPLE_CONTRACT,
    SAMPLE_REPORT
)

__all__ = [
    # Classifier schemas
    'Classification',
    'ClassificationMetadata',
    'ReviewDecision',

    # Email schemas
    'EmailDocument',
    'EmailMetadata',
    'EmailContent',
    'EmailAnalysis',
    'EmailAttachment',
    'SAMPLE_EMAIL',
    
    # JSON schemas
    'WebhookData',
    'APIResponse',
    'SystemEvent',
    'UserAction',
    'JSONAnalysis',
    'SAMPLE_WEBHOOK',
    'SAMPLE_API_RESPONSE',
    'SAMPLE_SYSTEM_EVENT',
    'SAMPLE_USER_ACTION',
    
    # PDF schemas
    'PDFDocument',
    'LineItem',
    'DocumentTotals',
    'ComplianceCheck',
    'DocumentMetadata',
    'PDFAnalysis',
    'SAMPLE_INVOICE',
    'SAMPLE_CONTRACT',
    'SAMPLE_REPORT'
] 