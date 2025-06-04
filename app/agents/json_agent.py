from typing import Dict, Any, List
import json
import google.generativeai as genai
import os
from jsonschema import validate, ValidationError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

class JSONAgent:
    """Agent responsible for processing and validating JSON data"""
    
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Common JSON schemas
        self.schemas = {
            "webhook": {
                "type": "object",
                "required": ["event_type", "timestamp", "data"],
                "properties": {
                    "event_type": {"type": "string"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {"type": "object"}
                }
            },
            "api_response": {
                "type": "object",
                "required": ["status", "data"],
                "properties": {
                    "status": {"type": "string"},
                    "data": {"type": "object"},
                    "error": {"type": "string"}
                }
            }
        }

    def process_json(self, json_content: str) -> Dict[str, Any]:
        """
        Process JSON content
        
        Args:
            json_content: Raw JSON content as string
            
        Returns:
            dict: Analysis results
        """
        try:
            # Parse JSON
            data = json.loads(json_content)
            
            # Analyze with Gemini
            prompt = f"""You are a JSON analysis expert. Your task is to:
1. Analyze the JSON structure
2. Identify key fields and their types
3. Detect potential anomalies or inconsistencies
4. Suggest data quality improvements
5. Extract business-relevant information

Provide your response in JSON format with the following structure:
{{
    "schema_analysis": {{
        "required_fields": [],
        "optional_fields": [],
        "field_types": {{}}
    }},
    "anomalies": [],
    "data_quality": {{
        "completeness": 0.8,
        "consistency": 0.9,
        "issues": []
    }},
    "business_context": {{
        "type": "webhook|api|config|other",
        "priority": "high|medium|low",
        "action_required": true
    }}
}}

JSON content to analyze:
{json_content[:1000]}"""

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
                    "schema_analysis": {
                        "required_fields": list(data.keys()) if isinstance(data, dict) else [],
                        "optional_fields": [],
                        "field_types": {k: type(v).__name__ for k, v in data.items()} if isinstance(data, dict) else {}
                    },
                    "anomalies": [],
                    "data_quality": {
                        "completeness": 0.8,
                        "consistency": 0.9,
                        "issues": []
                    },
                    "business_context": {
                        "type": "other",
                        "priority": "medium",
                        "action_required": False
                    }
                }
            
            # Validate against known schemas
            schema_validation = self._validate_against_schemas(data)
            
            # Check for anomalies
            anomalies = self._detect_anomalies(data)
            
            return {
                "status": "success",
                "analysis": analysis,
                "schema_validation": schema_validation,
                "anomalies": anomalies,
                "parsed_data": data
            }
            
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"Invalid JSON: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def _validate_against_schemas(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate JSON against known schemas"""
        results = {}
        
        for schema_name, schema in self.schemas.items():
            try:
                validate(instance=data, schema=schema)
                results[schema_name] = {"valid": True}
            except ValidationError as e:
                results[schema_name] = {
                    "valid": False,
                    "error": str(e)
                }
                
        return results

    def _detect_anomalies(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect anomalies in JSON data"""
        anomalies = []
        
        # Check for null values in required fields
        for schema_name, schema in self.schemas.items():
            if "required" in schema:
                for field in schema["required"]:
                    if field not in data or data[field] is None:
                        anomalies.append({
                            "type": "missing_required_field",
                            "field": field,
                            "schema": schema_name
                        })
        
        # Check for unexpected data types
        for key, value in data.items():
            if isinstance(value, (int, float)) and value < 0:
                anomalies.append({
                    "type": "negative_value",
                    "field": key,
                    "value": value
                })
            elif isinstance(value, str) and len(value) > 1000:
                anomalies.append({
                    "type": "long_string",
                    "field": key,
                    "length": len(value)
                })
                
        return anomalies

# Initialize JSON agent
json_agent = JSONAgent() 