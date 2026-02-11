import json
import logging
from config.manager import config_manager

logger = logging.getLogger(__name__)

class GCSHandler:
    def __init__(self):
        # 客户端由 ConfigManager 管理
        pass

    def _get_bucket(self):
        active_project = config_manager.get_active_project()
        if not active_project:
            raise ValueError("No active project configured.")
        
        client = config_manager.get_storage_client()
        return client.bucket(active_project['bucket_name'])

    def upload_jsonl(self, data: list, destination_blob_name: str) -> str:
        """上传 JSONL 并返回 gs:// URI"""
        try:
            bucket = self._get_bucket()
            blob = bucket.blob(destination_blob_name)
            
            # 确保没有 Markdown 污染，纯净 JSONL
            content = "\n".join([json.dumps(item, ensure_ascii=False) for item in data])
            blob.upload_from_string(content, content_type="application/jsonl")
            
            uri = f"gs://{bucket.name}/{destination_blob_name}"
            logger.info(f"Uploaded input to {uri}")
            return uri
        except Exception as e:
            logger.error(f"GCS Upload Failed: {e}")
            raise

    def read_batch_output(self, prefix: str) -> list:
        """读取 Vertex AI 输出目录下的所有 JSONL"""
        # 注意：prefix 必须以 / 结尾，例如 "uuid/stage_1/output/"
        try:
            bucket = self._get_bucket()
            blobs = list(bucket.list_blobs(prefix=prefix))
            results = []
            
            for blob in blobs:
                if blob.name.endswith(".jsonl") and "prediction-" in blob.name:
                    try:
                        content = blob.download_as_text()
                        for line in content.strip().split('\n'):
                            if line:
                                results.append(json.loads(line))
                    except Exception as e:
                        logger.error(f"Failed to parse blob {blob.name}: {e}")
            
            logger.info(f"Read {len(results)} items from {prefix}")
            return results
        except Exception as e:
            logger.error(f"GCS Read Failed: {e}")
            return []
