from fastapi import FastAPI, HTTPException
from typing import Optional
from services.dispatcher import dispatcher
from config.logging_config import setup_logging
from config.manager import config_manager
from config.settings import settings
import logging
import time

setup_logging()
logger = logging.getLogger("main")
app = FastAPI(title="Headless Chat Orchestrator")

@app.on_event("startup")
def startup_event():
    logger.info("Initializing Chat Orchestrator...")
    if not config_manager.initialized:
        config_manager.load_projects()

    logger.info(f"Active Project Pool Size: {len(config_manager.project_pool)}")

    if settings.BATCH_ENABLED:
        from scheduler import start_scheduler

        start_scheduler()
    else:
        logger.info("Batch mode disabled. Scheduler not started.")

@app.get("/health")
def health_check():
    return {
        "status": "ok", 
        "pool_size": len(config_manager.project_pool),
        "cooldown": time.time() < dispatcher.cooldown_until,
        "batch_enabled": settings.BATCH_ENABLED,
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

