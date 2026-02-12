from apscheduler.schedulers.background import BackgroundScheduler
from core.models import SessionLocal, BatchJob
from services.gcs_handler import GCSHandler
from services.vertex_handler import VertexHandler
from config.manager import config_manager
from config.settings import settings
from datetime import datetime
from typing import Any
import logging

logger = logging.getLogger("scheduler")

def process_pipelines():
    """Main Scheduler Loop"""
    db = SessionLocal()
    try:
        jobs = db.query(BatchJob).filter(BatchJob.status == "RUNNING").all()
        if not jobs:
            return

        if len(jobs) > settings.MAX_CONCURRENT_JOBS:
            logger.warning(
                f"RUNNING jobs exceed limit: {len(jobs)}/{settings.MAX_CONCURRENT_JOBS}"
            )

        gcs = GCSHandler()
        has_updates = False
        now = datetime.utcnow()

        for raw_job in jobs:
            job: Any = raw_job
            try:
                reference_time = job.updated_at or job.created_at or now
                if (now - reference_time).total_seconds() > settings.JOB_TIMEOUT_SECONDS:
                    logger.error(f"Job {job.id} TIMED OUT.")
                    job.status = "FAILED"
                    job.result_summary = "Timeout: Job stuck in RUNNING"
                    has_updates = True
                    continue

                project_context = config_manager.get_project_by_id(job.used_project_id)
                if not project_context:
                    logger.error(
                        f"Project {job.used_project_id} not found for Job {job.id}. Cannot check status."
                    )
                    continue

                if not job.vertex_job_id:
                    logger.error(f"Job {job.id} missing vertex_job_id. Marking as FAILED.")
                    job.status = "FAILED"
                    job.result_summary = "Missing Vertex job resource name"
                    has_updates = True
                    continue

                vertex = VertexHandler(project_context)
                state = vertex.get_job_status(job.vertex_job_id)

                if state == "JOB_STATE_SUCCEEDED":
                    logger.info(f"Job {job.id} SUCCEEDED")
                    job.status = "SUCCEEDED"

                    if job.output_gcs_uri:
                        prefix = job.output_gcs_uri.replace(
                            f"gs://{settings.BUCKET_NAME}/", "", 1
                        )
                        results = gcs.read_batch_output(prefix)
                        job.result_summary = f"Processed {len(results)} items."
                    else:
                        job.result_summary = "Completed, but output path is missing"

                    has_updates = True

                elif state in ["JOB_STATE_FAILED", "JOB_STATE_CANCELLED"]:
                    logger.warning(f"Job {job.id} matches Vertex State: {state}")
                    job.status = "FAILED"
                    job.result_summary = f"Vertex Job Failed: {state}"
                    has_updates = True
            except Exception as job_error:
                logger.error(f"Failed to process job {job.id}: {job_error}")

        if has_updates:
            db.commit()

    except Exception as e:
        db.rollback()
        logger.error(f"Scheduler Loop Error: {e}")
    finally:
        db.close()

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(process_pipelines, 'interval', minutes=1)
    scheduler.start()
