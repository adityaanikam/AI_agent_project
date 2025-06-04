#!/usr/bin/env python3
"""
Test PDF classifier specifically
"""
from app.agents.classifier_agent import classifier_agent

def test_pdf_classification():
    """Test the classifier with PDF-like content"""
    
    # Test with certificate content (like in user's screenshot)
    certificate_content = """
    INTERNSHIP COMPLETION CERTIFICATE
    
    This is to certify that [Student Name] has successfully completed 
    an internship program from [Start Date] to [End Date].
    
    During this period, the intern has demonstrated:
    - Technical skills
    - Professional behavior  
    - Achievement of objectives
    
    Certificate issued on: [Date]
    Authorized by: [Manager Name]
    """
    
    print("=== Testing Certificate PDF Classification ===")
    print(f"Input: {certificate_content[:100]}...")
    
    result = classifier_agent.classify(certificate_content)
    print(f"Result: {result}")
    
    # Test with invoice content
    invoice_content = """
    INVOICE #12345
    
    Bill To: Customer Company
    Amount: $15,000.00
    Due Date: 30 days
    
    Line Items:
    - Software License: $15,000.00
    
    Total Amount Due: $15,000.00
    """
    
    print("\n=== Testing Invoice PDF Classification ===")
    print(f"Input: {invoice_content[:50]}...")
    
    result = classifier_agent.classify(invoice_content)
    print(f"Result: {result}")

if __name__ == "__main__":
    test_pdf_classification() 