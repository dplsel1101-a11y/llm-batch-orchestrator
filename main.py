from fastapi import FastAPI, HTTPException, Depends
from typing import Optional
from sqlalchemy.orm import Session
from core.models import init_db, SessionLocal, BatchJob
from services.dispatcher import dispatcher
from scheduler import start_scheduler
from config.logging_config import setup_logging
from config.manager import config_manager
from config.settings import settings
import uuid
import logging
import time

setup_logging()
logger = logging.getLogger("main")
app = FastAPI(title="Headless Batch Orchestrator")

# Deps
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def startup_event():
    logger.info("Initializing Headless Orchestrator...")
    init_db() # Ensure tables exist
    
    # keys are already loaded by ConfigManager __init__ but we can force log
    logger.info(f"Active Project Pool Size: {len(config_manager.project_pool)}")
    
    start_scheduler()

@app.get("/health")
def health_check():
    return {
        "status": "ok", 
        "pool_size": len(config_manager.project_pool),
        "cooldown": time.time() < dispatcher.cooldown_until
    }

from pydantic import BaseModel

class ChatRequest(BaseModel):
    query: str
    # Dify might send 'inputs', 'query', or 'messages'. 
    # Adjust based on Dify spec or generic 'prompt'.
    sys_prompt: Optional[str] = None
    model: str = settings.MODEL_ID
    use_search: bool = True
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.95
    top_k: Optional[int] = 40
    thinking_level: Optional[str] = None

@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    if not config_manager.initialized:
        # Should be initialized by startup_event, but just in case
        config_manager.load_projects()

    if not config_manager.project_pool:
        logger.error("No projects available for chat.")
        raise HTTPException(status_code=503, detail="No active projects available.")
    
    try:
        response_text = dispatcher.dispatch_chat(
            prompt=request.query,
            model_id=request.model,
            sys_prompt=request.sys_prompt,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            thinking_level=request.thinking_level,
            use_search=request.use_search,
        )
        return response_text
        
    except Exception as e:
        logger.error(f"Chat Error: All projects failed chat. Last error: {e}")
        raise HTTPException(status_code=503, detail=f"All projects failed chat. Last error: {e}")

@app.post("/api/submit")
def submit_job(request: dict, db: Session = Depends(get_db)):
    """Async Job Submission via Dispatcher"""
    # 1. Init Record
    job_uuid = str(uuid.uuid4())
    new_job = BatchJob(
        id=job_uuid, # Schema changed from job_uuid to id
        status="PENDING",
    )
    db.add(new_job)
    db.commit()
    
    # 2. Dispatch
    try:
        result = dispatcher.submit_job(job_uuid, request, db)
        return result
    except Exception as e:
        logger.error(f"Dispatch Error: {e}")
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(BatchJob).filter(BatchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    status = str(job.status)
    
    return {
        "job_id": job.id,
        "status": status,
        "project": job.used_project_id,
        "vertex_job_id": job.vertex_job_id,
        "result_uri": job.output_gcs_uri if status == "SUCCEEDED" else None,
        "error": job.result_summary or ""
    }

