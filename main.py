from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, Dict, Any
import uvicorn
import os
import uuid
import logging
from datetime import datetime
from dotenv import load_dotenv

# Import our modules
from app.agents import classifier_agent, email_agent, json_agent, pdf_agent
from app.core import memory_manager, action_router
from app.schemas import EmailDocument, WebhookData, PDFDocument

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="FlowBit - Multi-Agent AI Processing System",
    description="Process various input formats using specialized AI agents",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for UI
app.mount("/static", StaticFiles(directory="static"), name="static")

async def process_file_async(
    file_content: bytes,
    file_name: str,
    process_id: str,
    process_type: Optional[str] = None
):
    """Background task for processing files"""
    try:
        # Step 1: Classify the input
        logger.info(f"Starting classification for {process_id}")
        
        # Handle different file types for classification
        if file_name.endswith('.pdf'):
            # For PDF files, pass the raw bytes
            classification = classifier_agent.classify(file_content.decode('utf-8', errors='ignore'))
        else:
            # For text files (JSON, EML), decode properly
            try:
                content_str = file_content.decode('utf-8')
            except UnicodeDecodeError:
                content_str = file_content.decode('latin-1', errors='ignore')
            classification = classifier_agent.classify(content_str)
        
        if classification["status"] == "error":
            raise Exception(f"Classification failed: {classification['error']}")
            
        # Store classification in memory
        memory_manager.update_record(process_id, {
            "classification": classification["classification"],
            "status": "classified"
        })
        
        # Step 2: Route to specialized agent
        input_type = classification["classification"]["input_type"]
        agent_output = None
        
        if input_type == "email":
            content_str = file_content.decode('utf-8', errors='ignore')
            agent_output = email_agent.process_email(content_str)
        elif input_type == "json":
            content_str = file_content.decode('utf-8', errors='ignore')
            agent_output = json_agent.process_json(content_str)
        elif input_type == "pdf":
            agent_output = await pdf_agent.process_pdf(file_content)
        else:
            raise ValueError(f"Unsupported input type: {input_type}")
            
        if agent_output["status"] == "error":
            raise Exception(f"Agent processing failed: {agent_output['error']}")
            
        # Store agent output in memory
        memory_manager.update_record(process_id, {
            "agent_output": agent_output,
            "status": "processed"
        })
        
        # Step 3: Route actions
        logger.info(f"Routing actions for {process_id}")
        actions = await action_router.process_agent_output(agent_output)
        
        # Store actions in memory
        memory_manager.update_record(process_id, {
            "actions_triggered": actions,
            "status": "completed"
        })
        
        logger.info(f"Processing completed for {process_id}")
        
    except Exception as e:
        logger.error(f"Error processing {process_id}: {str(e)}")
        memory_manager.update_record(process_id, {
            "status": "error",
            "error": str(e)
        })

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the upload UI"""
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <title>FlowBit - File Processing</title>
            <link rel="stylesheet" href="/static/style.css">
        </head>
        <body>
            <div class="container">
                <h1>FlowBit File Processing</h1>
                <form id="uploadForm">
                    <div class="form-group">
                        <label for="file">Select File:</label>
                        <input type="file" id="file" name="file" required>
                    </div>
                    <button type="submit">Process File</button>
                </form>
                <div id="status"></div>
                <div id="trace" class="trace"></div>
            </div>
            <script src="/static/app.js"></script>
        </body>
    </html>
    """

@app.post("/process")
async def process_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    process_type: Optional[str] = None
):
    """
    Process uploaded files using the appropriate agent
    
    Args:
        file: The file to process (Email, JSON, or PDF)
        process_type: Optional override for the processing type
    
    Returns:
        dict: Processing results and status
    """
    try:
        # Generate process ID
        process_id = str(uuid.uuid4())
        
        # Read file content
        content = await file.read()
        
        # Create initial record
        memory_manager.create_record(
            process_id=process_id,
            input_type=process_type or "unknown",
            metadata={
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(content)
            }
        )
        
        # Start background processing
        background_tasks.add_task(
            process_file_async,
            content,
            file.filename,
            process_id,
            process_type
        )
        
        return {
            "status": "processing",
            "process_id": process_id,
            "message": "File processing started"
        }
        
    except Exception as e:
        logger.error(f"Error starting processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{process_id}")
async def get_status(process_id: str):
    """
    Get the status of a processing job
    
    Args:
        process_id: The ID of the processing job
    
    Returns:
        dict: Current status and results if available
    """
    try:
        record = memory_manager.get_record(process_id)
        if not record:
            raise HTTPException(status_code=404, detail="Process not found")
            
        return {
            "process_id": process_id,
            "status": record.status,
            "classification": record.classification,
            "agent_output": record.agent_output,
            "actions_triggered": record.actions_triggered,
            "error": record.error,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history")
async def get_history():
    """
    Get processing history
    
    Returns:
        list: List of processed items
    """
    try:
        records = memory_manager.get_history()
        return {
            "history": [
                {
                    "process_id": record.process_id,
                    "input_type": record.input_type,
                    "status": record.status,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat()
                }
                for record in records
            ]
        }
    except Exception as e:
        logger.error(f"Error getting history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 