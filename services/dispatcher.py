import time
import random
import logging
from typing import Dict, Any, Optional
from services.vertex_handler import VertexHandler
from services.gcs_handler import GCSHandler
from services.pipeline_logic import PipelineLogic
from config.manager import config_manager
from config.settings import settings
from core.models import BatchJob

logger = logging.getLogger("services.dispatcher")

class Dispatcher:
    def __init__(self):
        self.cooldown_until = 0

    def submit_job(self, job_uuid: str, request_data: Dict[str, Any], db) -> Dict[str, Any]:
        """
        Orchestrate Job Submission:
        1. Upload Input to GCS (Shared)
        2. Loop through Projects to Submit Vertex Job
        """
        job = db.query(BatchJob).filter(BatchJob.id == job_uuid).first()
        if not job:
            raise ValueError(f"Job {job_uuid} not found in DB")

        # 1. Global Cooldown Check
        if time.time() < self.cooldown_until:
            remaining = int(self.cooldown_until - time.time())
            message = f"System in cooldown (60s). Retry in {remaining}s"
            job.status = "FAILED"
            job.result_summary = message
            db.commit()
            raise Exception(message)

        running_count = db.query(BatchJob).filter(BatchJob.status == "RUNNING").count()
        if running_count >= settings.MAX_CONCURRENT_JOBS:
            message = f"Max concurrent jobs reached ({settings.MAX_CONCURRENT_JOBS}). Retry later."
            job.status = "FAILED"
            job.result_summary = message
            db.commit()
            raise Exception(message)

        # 2. Upload to GCS (Once)
        try:
            gcs = GCSHandler()
            # Construct input items for Stage 1
            # Note: PipelineLogic.build_input_for_stage requires original request structure
            input_items = [PipelineLogic.build_input_for_stage(1, original_request={**request_data, "id": job_uuid})]
            
            input_uri = gcs.upload_jsonl(input_items, f"{job_uuid}/stage_1/input.jsonl")
            job.input_gcs_uri = input_uri
            db.commit()
        except Exception as e:
            logger.error(f"GCS Upload Failed: {e}")
            job.status = "FAILED"
            job.result_summary = f"GCS Upload Failed: {e}"
            db.commit()
            raise

        # 3. Project Selection Loop
        pool = config_manager.project_pool.copy()
        if not pool:
            message = "No active projects loaded."
            job.status = "FAILED"
            job.result_summary = message
            db.commit()
            raise Exception(message)
        
        random.shuffle(pool)
        
        last_error = ""
        for project_ctx in pool:
            project_id = project_ctx["project_id"]
            try:
                logger.info(f"Dispatching Job {job_uuid} to {project_id}...")
                
                vertex = VertexHandler(project_ctx)
                job_name = f"stage-1-{job_uuid}"
                output_prefix = f"gs://{settings.BUCKET_NAME}/{job_uuid}/stage_1/output/"
                
                # Submit
                vertex_job_id = vertex.submit_job(
                    job_name=job_name,
                    model_id=settings.MODEL_ID, 
                    input_uri=input_uri, 
                    output_prefix=output_prefix
                )
                
                # Success
                job.status = "RUNNING"
                job.used_project_id = project_id
                job.vertex_job_id = vertex_job_id
                job.output_gcs_uri = output_prefix
                db.commit()
                
                return {"job_uuid": job_uuid, "status": "STARTED", "project": project_id}

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Failed on {project_id}: {last_error}")
                # Continue to next project

        # 4. All Failed
        logger.error("All projects failed. Triggering Cooldown.")
        self.cooldown_until = time.time() + 60
        
        job.status = "FAILED"
        job.result_summary = f"All projects failed: {last_error or 'Unknown error'}"
        db.commit()
        raise Exception(job.result_summary)

    def dispatch_chat(
        self,
        prompt: str,
        model_id: str = settings.MODEL_ID,
        sys_prompt: Optional[str] = None,
        temperature: Optional[float] = 0.7,
        top_p: Optional[float] = 0.95,
        top_k: Optional[int] = 40,
        thinking_level: Optional[str] = None,
        use_search: bool = True,
    ) -> Dict[str, Any]:
        """
        Dispatch Chat Request with Retry Logic
        """
        # 1. Global Cooldown (Reuse same logic or separate?)
        # Let's share cooldown for simplicity
        if time.time() < self.cooldown_until:
             raise Exception("System in cooldown.")

        pool = config_manager.project_pool.copy()
        if not pool:
            raise Exception("No active projects loaded.")
        
        random.shuffle(pool)
        
        last_error = ""
        for project_ctx in pool:
            project_id = project_ctx["project_id"]
            try:
                # logger.info(f"Chat routed to {project_id}") # Optional: Too noisy for chat?
                vertex = VertexHandler(project_ctx)
                return vertex.chat_completion(
                    model_id=model_id,
                    prompt=prompt,
                    sys_prompt=sys_prompt,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    thinking_level=thinking_level,
                    use_search=use_search,
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Chat failed on {project_id}: {last_error}")
                # Continue
        
        # All failed
        self.cooldown_until = time.time() + 60
        raise Exception(f"All projects failed chat. Last error: {last_error}")

dispatcher = Dispatcher()

