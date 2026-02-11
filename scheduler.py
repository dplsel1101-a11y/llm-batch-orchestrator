from apscheduler.schedulers.background import BackgroundScheduler
from core.models import SessionLocal, BatchJob
from services.gcs_handler import GCSHandler
from services.vertex_handler import VertexHandler
from services.pipeline_logic import PipelineLogic
from config.settings import settings
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def process_pipelines():
    """主调度循环"""
    db = SessionLocal()
    try:
        # 1. 并发控制
        running_count = db.query(BatchJob).filter(BatchJob.status == "RUNNING").count()
        if running_count >= settings.MAX_CONCURRENT_JOBS:
            logger.info(f"Concurrency limit reached ({running_count}/{settings.MAX_CONCURRENT_JOBS}). Skipping cycle.")
            return

        # 2. 获取运行中的任务
        jobs = db.query(BatchJob).filter(BatchJob.status == "RUNNING").all()
        
        # 确保有活跃的项目上下文，否则跳过
        from config.manager import config_manager
        if not config_manager.get_active_project():
             # 尝试加载（如果是第一次运行或重启后）
            try:
                config_manager.reload_context()
            except Exception:
                pass
            
            if not config_manager.get_active_project():
                logger.warning("No active project context. Skipping scheduler cycle.")
                return

        # Handlers 会自动使用 ConfigManager
        vertex = VertexHandler()
        gcs = GCSHandler()

        for job in jobs:
            # --- 僵尸任务熔断 ---
            if (datetime.utcnow() - job.updated_at).total_seconds() > settings.JOB_TIMEOUT_SECONDS:
                logger.error(f"Job {job.job_uuid} TIMED OUT. Marking FAILED.")
                job.status = "FAILED"
                job.last_error = "Timeout: Job stuck in RUNNING for too long"
                db.commit()
                continue

            # --- 状态检查 ---
            state = vertex.get_job_status(job.vertex_job_name)
            
            if state == "JOB_STATE_SUCCEEDED":
                logger.info(f"Job {job.job_uuid} Stage {job.current_stage} SUCCEEDED")
                
                # 下载结果
                output_prefix = f"{job.gcs_prefix}stage_{job.current_stage}/output/"
                results = gcs.read_batch_output(output_prefix)
                
                if not results:
                    _handle_failure(db, job, "No output files found in GCS")
                    continue

                # 准备下一阶段
                next_stage = job.current_stage + 1
                if next_stage > 7:
                    job.status = "COMPLETED"
                    job.current_stage = 7
                    db.commit()
                    continue
                
                # 生成下一阶段输入
                next_inputs = []
                for res in results:
                    valid, msg = PipelineLogic.validate_output(job.current_stage, res)
                    if valid:
                        next_inputs.append(PipelineLogic.build_input_for_stage(next_stage, previous_output=res))
                    else:
                        logger.warning(f"Item validation failed: {msg}")
                
                if not next_inputs:
                    _handle_failure(db, job, "All items failed validation")
                    continue

                # 提交下一阶段
                try:
                    input_uri = gcs.upload_jsonl(next_inputs, f"{job.job_uuid}/stage_{next_stage}/input.jsonl")
                    job_name = f"stage-{next_stage}-{job.job_uuid}"
                    new_job_id = vertex.submit_job(job_name, input_uri, f"{job.job_uuid}/stage_{next_stage}/output/")
                    
                    job.vertex_job_name = new_job_id
                    job.current_stage = next_stage
                    # updated_at 会自动更新
                    db.commit()
                except Exception as e:
                    _handle_failure(db, job, f"Submission failed: {str(e)}")

            elif state in ["JOB_STATE_FAILED", "JOB_STATE_CANCELLED"]:
                _handle_failure(db, job, f"Vertex Job Failed with state {state}")

    except Exception as e:
        logger.error(f"Scheduler Loop Error: {e}")
    finally:
        db.close()

def _handle_failure(db, job, error_msg):
    """重试逻辑"""
    if job.retry_count < 3:
        job.retry_count += 1
        logger.warning(f"Job {job.job_uuid} failed. Retrying ({job.retry_count}/3). Error: {error_msg}")
        # 这里可以添加重新提交当前阶段的逻辑
        # 为简单起见，暂时保持 RUNNING 状态，下个周期如果 Vertex 状态仍是 FAILED 再处理
        # 实际生产建议：重新生成 Vertex Job ID
    else:
        job.status = "FAILED"
        job.last_error = error_msg
    db.commit()

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(process_pipelines, 'interval', minutes=1)
    scheduler.start()
