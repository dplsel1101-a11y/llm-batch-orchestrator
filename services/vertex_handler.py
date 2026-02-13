from google.cloud import aiplatform
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class VertexHandler:
    def __init__(self, project_context: Optional[Dict[str, Any]] = None):
        """
        :param project_context: Dict containing 'project_id', 'credentials', 'region'
        """
        self.context = project_context

    def _require_context(self) -> Dict[str, Any]:
        if self.context is None:
            raise ValueError("VertexHandler requires a project_context to operate.")
        return self.context

    @staticmethod
    def _build_chat_model_path(model_id: str) -> str:
        normalized = model_id.strip()
        if not normalized:
            raise ValueError("model_id cannot be empty")

        if normalized.startswith("projects/"):
            return normalized
        if normalized.startswith("publishers/"):
            return normalized
        if normalized.startswith("models/"):
            return f"publishers/google/{normalized}"
        return f"publishers/google/models/{normalized}"

    def _init_client(self):
        context = self._require_context()
        
        aiplatform.init(
            project=context['project_id'],
            location=context['region'],
            credentials=context['credentials']
        )

    def submit_job(self, job_name: str, model_id: str, input_uri: str, output_prefix: str) -> str:
        self._init_client()
        context = self._require_context()
        
        # Check bucket name for destination (handled by Dispatcher constructing the prefix, 
        # but here we need to ensure the prefix is full gs:// URI)
        # The caller (Dispatcher) passes fully qualified URIs? 
        # Old code: f"gs://{active_project['bucket_name']}/{output_prefix}"
        # We should let caller handle bucket name or pass it in context.
        # But wait, Dispatcher knows the bucket name.
        
        try:
            job = aiplatform.BatchPredictionJob.create(
                job_display_name=job_name,
                model_name=model_id,
                instances_format="jsonl",
                gcs_source=[input_uri],
                predictions_format="jsonl",
                gcs_destination_prefix=output_prefix, # Expecting gs://...
                sync=False,
            )

            resource_name = getattr(job, "resource_name", None) or getattr(job, "name", None)
            if not resource_name:
                for _ in range(6):
                    time.sleep(0.5)
                    resource_name = getattr(job, "resource_name", None) or getattr(job, "name", None)
                    if resource_name:
                        break

            if not resource_name:
                raise RuntimeError("Vertex job created, but resource name is unavailable")

            logger.info(f"Submitted Vertex Job: {resource_name} in {context['project_id']}")
            return resource_name
        except Exception as e:
            logger.error(f"Vertex Submit Failed on {context['project_id']}: {e}")
            raise

    def get_job_status(self, job_resource_name: str) -> str:
        self._init_client()
        context = self._require_context()
        try:
            job = aiplatform.BatchPredictionJob(
                job_resource_name,
                project=context['project_id'],
                location=context['region'],
                credentials=context['credentials'],
            )
            return job.state.name
        except Exception as e:
            # If 403 or 404, it might be the wrong project or job deleted
            logger.error(f"Vertex Status Check Failed ({job_resource_name}): {e}")
            return "UNKNOWN"

    def chat_completion(self, model_id: str, prompt: str, 
                        sys_prompt: Optional[str] = None, 
                        temperature: Optional[float] = 0.7,
                        top_p: Optional[float] = 0.95,
                        top_k: Optional[int] = 40,
                        thinking_level: Optional[str] = None,
                        use_search: bool = True) -> dict:
        """
        Real-time Chat via Direct REST API (v1beta1)
        Matches user's exact payload structure.
        """
        import requests
        from google.auth.transport.requests import Request

        try:
            context = self._require_context()

            creds = context['credentials']
            if not creds.valid:
                creds.refresh(Request())
            
            access_token = creds.token
            project_id = context['project_id']
            region = context['region']
            
            # Host logic
            if region == "global":
                base_host = "aiplatform.googleapis.com"
            else:
                base_host = f"{region}-aiplatform.googleapis.com"

            # URL construction
            model_path = self._build_chat_model_path(model_id)
            url = f"https://{base_host}/v1beta1/projects/{project_id}/locations/{region}/{model_path}:generateContent"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # 1. generationConfig
            gen_config = {
                "temperature": 0.7 if temperature is None else temperature,
                "topP": 0.95 if top_p is None else top_p,
                "topK": 40 if top_k is None else top_k,
            }
            
            if thinking_level:
                gen_config["thinkingConfig"] = {
                    "thinkingLevel": thinking_level.upper()
                }

            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": gen_config
            }
            
            # 2. System Prompt
            if sys_prompt:
                payload["systemInstruction"] = {
                    "parts": [{"text": sys_prompt}]
                }

            # 3. Google Search
            if use_search:
                payload["tools"] = [{
                    "googleSearch": {} 
                }]

            # requests respects env vars for proxy
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code != 200:
                 logger.error(f"Google API Error {response.status_code}: {response.text}")
                 raise Exception(f"Google API Error: {response.text}")
            
            result = response.json()
            
            # Parse result matching user's script
            try:
                candidates = result.get("candidates", [])
                if not candidates:
                     return {"answer": "Error: No candidates returned", "sources": []}
                
                candidate = candidates[0]
                
                # Safety/Finish Reason
                if "content" not in candidate:
                    finish_reason = candidate.get("finishReason", "UNKNOWN")
                    return {"answer": f"Blocked: {finish_reason}", "sources": []}

                answer_text = ""
                if "parts" in candidate["content"]:
                    for part in candidate["content"]["parts"]:
                         if "text" in part:
                             answer_text += part["text"]
                
                sources = []
                if "groundingMetadata" in candidate:
                    # Some versions use groundingChunks, others might differ. 
                    # User script uses groundingChunks.
                    chunks = candidate["groundingMetadata"].get("groundingChunks", [])
                    for chunk in chunks:
                        if "web" in chunk:
                            sources.append({
                                "title": chunk["web"].get("title", "网页链接"),
                                "url": chunk["web"]["uri"]
                            })
                
                return {
                    "answer": answer_text,
                    "sources": sources,
                    "used_account": project_id,
                    "region": region
                }
            except Exception as e:
                 logger.error(f"Parsing Error: {e}")
                 return {"answer": f"Parsing Failed: {str(e)}", "sources": [], "raw": str(result)}

        except Exception as e:
            project_id = "unknown"
            if self.context is not None:
                project_id = self.context.get("project_id", "unknown")
            logger.error(f"Vertex Chat Failed on {project_id}: {e}")
            raise

