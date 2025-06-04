from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

class EmailAttachment(BaseModel):
    """Schema for email attachments"""
    filename: str
    content_type: str
    size: int
    content: bytes

class EmailMetadata(BaseModel):
    """Schema for email metadata"""
    from_address: EmailStr
    to_addresses: List[EmailStr]
    cc_addresses: Optional[List[EmailStr]] = []
    bcc_addresses: Optional[List[EmailStr]] = []
    subject: str
    date: datetime
    message_id: str
    in_reply_to: Optional[str] = None
    references: Optional[List[str]] = []

class EmailContent(BaseModel):
    """Schema for email content"""
    text_content: str
    html_content: Optional[str] = None
    attachments: Optional[List[EmailAttachment]] = []

class EmailAnalysis(BaseModel):
    """Schema for email analysis results"""
    tone: str = Field(..., pattern="^(formal|informal|urgent|neutral)$")
    urgency: str = Field(..., pattern="^(high|medium|low)$")
    sentiment: str = Field(..., pattern="^(positive|negative|neutral)$")
    key_topics: List[str]
    action_items: List[str]
    entities: dict

class EmailDocument(BaseModel):
    """Complete email document schema"""
    metadata: EmailMetadata
    content: EmailContent
    analysis: Optional[EmailAnalysis] = None

# Sample email format
SAMPLE_EMAIL = {
    "metadata": {
        "from_address": "sender@example.com",
        "to_addresses": ["recipient@example.com"],
        "cc_addresses": ["cc@example.com"],
        "subject": "Important Update",
        "date": "2024-02-20T10:00:00Z",
        "message_id": "<123456@example.com>"
    },
    "content": {
        "text_content": "Dear Team,\n\nThis is an important update regarding our project timeline.\n\nBest regards,\nSender",
        "html_content": "<p>Dear Team,</p><p>This is an important update regarding our project timeline.</p><p>Best regards,<br>Sender</p>",
        "attachments": [
            {
                "filename": "update.pdf",
                "content_type": "application/pdf",
                "size": 1024
            }
        ]
    }
} 