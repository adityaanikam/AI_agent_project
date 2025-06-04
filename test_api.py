#!/usr/bin/env python3
"""
Test script for FlowBit API
"""
import requests
import time
import json

API_BASE = "http://localhost:8000"

def test_file_upload(filename: str, file_type: str):
    """Test file upload and processing"""
    print(f"\n=== Testing {file_type} file: {filename} ===")
    
    # Upload file
    with open(filename, 'rb') as f:
        files = {'file': (filename, f, 'application/octet-stream')}
        response = requests.post(f"{API_BASE}/process", files=files)
    
    if response.status_code == 200:
        result = response.json()
        process_id = result.get('process_id')
        print(f"✅ Upload successful! Process ID: {process_id}")
        
        # Poll for status
        max_polls = 30
        for i in range(max_polls):
            status_response = requests.get(f"{API_BASE}/status/{process_id}")
            if status_response.status_code == 200:
                status_data = status_response.json()
                current_status = status_data.get('status')
                print(f"📊 Status check {i+1}: {current_status}")
                
                if current_status in ['completed', 'error']:
                    print(f"🎯 Final result:")
                    print(json.dumps(status_data, indent=2))
                    break
                    
            time.sleep(2)
        else:
            print("⏰ Timeout waiting for completion")
    else:
        print(f"❌ Upload failed: {response.status_code} - {response.text}")

def test_api():
    """Test all API endpoints"""
    print("🚀 Starting FlowBit API Tests")
    
    # Test root endpoint
    try:
        response = requests.get(f"{API_BASE}/")
        print(f"✅ Root endpoint: {response.status_code}")
    except Exception as e:
        print(f"❌ Root endpoint failed: {e}")
        return
    
    # Test file uploads
    test_files = [
        ("test_sample.json", "JSON"),
        ("test_sample.eml", "Email"),
        ("test_sample.pdf", "PDF")
    ]
    
    for filename, file_type in test_files:
        try:
            test_file_upload(filename, file_type)
        except Exception as e:
            print(f"❌ Error testing {filename}: {e}")
    
    # Test history endpoint
    try:
        response = requests.get(f"{API_BASE}/history")
        if response.status_code == 200:
            history = response.json()
            print(f"\n📚 History endpoint: {len(history.get('history', []))} records")
        else:
            print(f"❌ History endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ History endpoint error: {e}")

if __name__ == "__main__":
    test_api() 