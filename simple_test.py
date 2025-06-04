#!/usr/bin/env python3
"""
Simple Gemini API test
"""
import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_simple_gemini():
    """Test basic Gemini functionality"""
    
    # Check API key
    api_key = os.getenv("GOOGLE_API_KEY")
    print(f"API Key loaded: {'Yes' if api_key else 'No'}")
    if api_key:
        print(f"API Key length: {len(api_key)}")
    
    # Configure Gemini
    genai.configure(api_key=api_key)
    
    try:
        # Initialize model
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Simple prompt
        prompt = "Return only this JSON: {\"test\": \"working\"}"
        
        print(f"Sending prompt: {prompt}")
        response = model.generate_content(prompt)
        
        print(f"Raw response: '{response.text}'")
        print(f"Response type: {type(response.text)}")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    test_simple_gemini() 