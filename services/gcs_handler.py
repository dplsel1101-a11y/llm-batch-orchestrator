import json
import logging
from config.manager import config_manager
from config.settings import settings

logger = logging.getLogger(__name__)

class GCSHandler:
    def __init__(self):
        pass

    def _get_bucket(self):
        # Allow any available credentials to access the shared bucket
        client = config_manager.get_storage_client()
        return client.bucket(settings.BUCKET_NAME)

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
            results = []
            
            for blob in bucket.list_blobs(prefix=prefix):
                if blob.name.endswith(".jsonl") and "prediction-" in blob.name:
                    try:
                        content = blob.download_as_text()
                        for line in content.splitlines():
                            payload = line.strip()
                            if payload:
                                results.append(json.loads(payload))
                    except Exception as e:
                        logger.error(f"Failed to parse blob {blob.name}: {e}")
            
            logger.info(f"Read {len(results)} items from {prefix}")
            return results
        except Exception as e:
            logger.error(f"GCS Read Failed: {e}")
            return []

