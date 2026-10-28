from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from typing import Optional
import uvicorn
import os
import uuid
import logging
import threading
from dotenv import load_dotenv

# Load environment variables before the modules that read them
load_dotenv()

# Import our modules
from app.core import memory_manager
from app.graph import create_runner
from app.schemas import ReviewDecision

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Runs the LangGraph pipeline; checkpoints go to FLOWBIT_CHECKPOINT_DB
runner = create_runner(memory_manager)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Resume runs a crash or restart left unfinished"""
    if os.getenv("FLOWBIT_RESUME_ON_STARTUP", "1") != "0":
        threading.Thread(target=runner.resume_incomplete, daemon=True).start()
    yield

# Initialize FastAPI app
app = FastAPI(
    title="FlowBit - Multi-Agent AI Processing System",
    description="Process various input formats using specialized AI agents",
    version="1.0.0",
    lifespan=lifespan
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
            runner.start,
            process_id,
            file.filename or "",
            content
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
            "review_request": runner.pending_review(process_id) if record.status == "awaiting_review" else None,
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

@app.post("/review/{process_id}")
async def review(process_id: str, decision: ReviewDecision, background_tasks: BackgroundTasks):
    """
    Resume a run paused for review (low classifier confidence or a risky action)
    
    Args:
        process_id: The ID of the paused processing job
        decision: approved, plus optional input_type / business_intent corrections
    
    Returns:
        dict: Processing status
    """
    if not memory_manager.get_record(process_id):
        raise HTTPException(status_code=404, detail="Process not found")
    if runner.pending_review(process_id) is None:
        raise HTTPException(status_code=409, detail="Process is not waiting for review")
    background_tasks.add_task(runner.review, process_id, decision.model_dump(exclude_none=True))
    return {"status": "processing", "process_id": process_id, "message": "Review submitted"}

@app.post("/resume/{process_id}")
async def resume(process_id: str, background_tasks: BackgroundTasks):
    """
    Continue a failed or interrupted run from its last checkpoint
    
    Args:
        process_id: The ID of the processing job
    
    Returns:
        dict: Processing status
    """
    if not memory_manager.get_record(process_id):
        raise HTTPException(status_code=404, detail="Process not found")
    if not runner.can_resume(process_id):
        raise HTTPException(status_code=409, detail="Process has no unfinished checkpoint to resume")
    background_tasks.add_task(runner.resume, process_id)
    return {"status": "processing", "process_id": process_id, "message": "Resuming from checkpoint"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 