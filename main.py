from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from core.models import init_db, SessionLocal, BatchJob
from services.gcs_handler import GCSHandler
from services.vertex_handler import VertexHandler
from services.pipeline_logic import PipelineLogic
from scheduler import start_scheduler
from config.logging_config import setup_logging
from config.settings import settings
from config.manager import config_manager
from api.admin import router as admin_router
import uuid
import logging

# 初始化
setup_logging()
logger = logging.getLogger("main")
app = FastAPI(title="Vertex AI Batch Orchestrator")

# Mount Static Files (Admin UI)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include Routers
app.include_router(admin_router)

# 依赖注入
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def startup_event():
    logger.info("Starting up... Initializing DB and Scheduler")
    init_db()
    
    # 尝试加载上次活跃的配置（如果有）
    try:
        config_manager.reload_context()
    except Exception as e:
        logger.warning(f"Could not load active project context on startup: {e}")
        
    start_scheduler()

@app.get("/admin", include_in_schema=False)
async def admin_page():
    return FileResponse("static/admin.html")

@app.get("/health")
def health_check():
    """ECS 健康检查"""
    return {"status": "ok", "service": "batch-orchestrator"}

@app.post("/api/submit")
def submit_job(request: dict, db: Session = Depends(get_db)):
    """提交新任务"""
    job_uuid = str(uuid.uuid4())
    logger.info(f"Received submission: {job_uuid}")
    
    # 1. 创建 DB 记录
    new_job = BatchJob(
        job_uuid=job_uuid,
        current_stage=0,
        status="PENDING",
        gcs_prefix=f"{job_uuid}/"
    )
    db.add(new_job)
    db.commit()
    
    try:
        # 2. 准备 Stage 1
        gcs = GCSHandler()
        # 构造带有 custom_id 的输入
        input_data = [PipelineLogic.build_input_for_stage(1, original_request={**request, "id": job_uuid})]
        input_uri = gcs.upload_jsonl(input_data, f"{job_uuid}/stage_1/input.jsonl")
        
        # 3. 提交 Vertex Job
        vertex = VertexHandler()
        job_name = f"stage-1-{job_uuid}"
        vertex_job_id = vertex.submit_job(job_name, input_uri, f"{job_uuid}/stage_1/output/")
        
        # 4. 更新状态
        new_job.vertex_job_name = vertex_job_id
        new_job.current_stage = 1
        new_job.status = "RUNNING"
        db.commit()
        
        return {"job_uuid": job_uuid, "status": "STARTED"}
        
    except Exception as e:
        logger.error(f"Submission failed: {e}")
        new_job.status = "FAILED"
        new_job.last_error = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/{job_uuid}")
def get_job_status(job_uuid: str, db: Session = Depends(get_db)):
    """查询状态"""
    job = db.query(BatchJob).filter(BatchJob.job_uuid == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_uuid": job.job_uuid,
        "status": job.status,
        "current_stage": job.current_stage,
        "last_error": job.last_error,
        "updated_at": job.updated_at,
        "result_uri": f"gs://{settings.BUCKET_NAME}/{job.job_uuid}/stage_7/output/" if job.status == "COMPLETED" else None
    }
