#!/usr/bin/env python3
"""
Test Gemini API connection
"""
import os
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate

# Load environment variables
load_dotenv()

async def test_gemini():
    """Test basic Gemini functionality"""
    
    # Check API key
    api_key = os.getenv("GOOGLE_API_KEY")
    print(f"API Key loaded: {'Yes' if api_key else 'No'}")
    if api_key:
        print(f"API Key length: {len(api_key)}")
        print(f"API Key starts with: {api_key[:10]}...")
    
    # Configure Gemini
    genai.configure(api_key=api_key)
    
    # List available models
    try:
        print("\nAvailable models:")
        for model in genai.list_models():
            if 'generateContent' in model.supported_generation_methods:
                print(f"- {model.name}")
    except Exception as e:
        print(f"Error listing models: {e}")
    
    # Test with different model names
    model_names = [
        "gemini-1.5-flash",
        "gemini-1.5-pro", 
        "gemini-pro",
        "models/gemini-pro",
        "models/gemini-1.5-flash"
    ]
    
    for model_name in model_names:
        try:
            print(f"\nTesting model: {model_name}")
            # Initialize model
            model = ChatGoogleGenerativeAI(
                model=model_name,
                temperature=0.1,
                convert_system_message_to_human=True
            )
            
            # Create simple prompt
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a helpful assistant. Respond with only valid JSON."),
                ("human", "Return this JSON: {{\"input_type\": \"email\", \"confidence\": 0.9}}")
            ])
            
            messages = prompt.format_messages()
            print("Sending request to Gemini...")
            
            response = await model.ainvoke(messages)
            print(f"✅ Success! Response: {response.content}")
            return model_name
            
        except Exception as e:
            print(f"❌ Failed with {model_name}: {e}")
    
    return None

if __name__ == "__main__":
    asyncio.run(test_gemini()) 