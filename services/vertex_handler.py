from google.cloud import aiplatform
from config.manager import config_manager
import logging
import time

logger = logging.getLogger(__name__)

class VertexHandler:
    def __init__(self):
        # 初始化移交给了 ConfigManager
        pass

    def submit_job(self, job_name: str, input_uri: str, output_prefix: str) -> str:
        """提交 Batch Prediction Job"""
        active_project = config_manager.get_active_project()
        if not active_project:
            raise ValueError("No active project configured. Please set one in Admin Panel.")

        # 确保当前线程/进程的 SDK 已初始化
        config_manager.init_aiplatform()

        try:
            job = aiplatform.BatchPredictionJob.create(
                job_display_name=job_name,
                model_name="publishers/google/models/gemini-3-flash-preview", # 这里可以考虑从 Config 读取模型
                instances_format="jsonl",
                gcs_source=[input_uri],
                predictions_format="jsonl",
                gcs_destination_prefix=f"gs://{active_project['bucket_name']}/{output_prefix}",
                sync=False,
                project=active_project['project_id'],
                location=active_project['region']
            )
            
            # WORKAROUND: with sync=False, the SDK might not populate resource_name immediately
            time.sleep(5)
            
            logger.info(f"Submitted Vertex Job: {job.resource_name}")
            return job.resource_name
        except Exception as e:
            logger.error(f"Vertex Submit Failed: {e}")
            raise

    def get_job_status(self, job_resource_name: str) -> str:
        """获取任务状态"""
        try:
            # 确保初始化
            config_manager.init_aiplatform()
            
            job = aiplatform.BatchPredictionJob(job_resource_name)
            return job.state.name
        except Exception as e:
            logger.error(f"Vertex Status Check Failed: {e}")
            return "UNKNOWN"
