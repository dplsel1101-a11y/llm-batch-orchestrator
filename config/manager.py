import os
import json
import glob
import random
from typing import List, Dict, Optional
from google.oauth2 import service_account
from google.cloud import storage
from config.settings import settings
import logging

logger = logging.getLogger("config.manager")

class ConfigManager:
    """
    Headless Config Manager.
    Loads Service Account Keys from `json/{ACTIVE_KEY_GROUP}/` directory.
    Manages Global Proxy.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
            
        self.project_pool: List[Dict] = []
        self.project_map: Dict[str, Dict] = {}
        self._storage_clients: Dict[str, storage.Client] = {}
        self.apply_proxy()
        self.load_projects()
        self.initialized = True

    def apply_proxy(self):
        """Apply HTTPS_PROXY from settings to environment variables."""
        if settings.HTTPS_PROXY:
            logger.info(f"Applying Global Proxy: {settings.HTTPS_PROXY}")
            os.environ["https_proxy"] = settings.HTTPS_PROXY
            os.environ["http_proxy"] = settings.HTTPS_PROXY
            os.environ["HTTPS_PROXY"] = settings.HTTPS_PROXY
            os.environ["HTTP_PROXY"] = settings.HTTPS_PROXY
        else:
            logger.info("No Proxy Configured (Direct Connect).")

    def load_projects(self):
        """Scan json/{ACTIVE_KEY_GROUP} for .json key files."""
        self.project_pool = []
        self.project_map = {}
        self._storage_clients = {}
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Adjust path to match docker layout or local
        # Assuming /app/json inside docker, or ./json locally
        key_dir = os.path.join(base_dir, "json", settings.ACTIVE_KEY_GROUP)
        
        logger.info(f"Scanning for keys in: {key_dir}")
        
        if not os.path.exists(key_dir):
            logger.warning(f"Key directory not found: {key_dir} (This is expected during build/test if keys aren't mounted yet)")
            return

        key_files = glob.glob(os.path.join(key_dir, "*.json"))
        logger.info(f"Found {len(key_files)} key files.")
        
        for key_path in key_files:
            try:
                with open(key_path, 'r') as f:
                    key_data = json.load(f)
                
                project_id = key_data.get("project_id")
                if not project_id:
                    logger.warning(f"File {key_path} is missing 'project_id', skipping.")
                    continue

                # Filter AI Studio Keys (gen-lang-client) as per user request
                if "gen-lang-client" in str(project_id):
                    logger.info(f"Skipping AI Studio Key: {project_id}")
                    continue
                
                credentials = service_account.Credentials.from_service_account_info(
                    key_data,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                
                project_context = {
                    "project_id": project_id,
                    "credentials": credentials,
                    "key_path": key_path,
                    "region": settings.REGION
                }
                self.project_pool.append(project_context)
                self.project_map[project_id] = project_context
                logger.info(f"Loaded Project: {project_id}")
                
            except Exception as e:
                logger.error(f"Failed to load key {key_path}: {e}")

        logger.info(f"Successfully loaded {len(self.project_pool)} projects into pool.")
        
        # Ensure Bucket Exists
        if self.project_pool and settings.BUCKET_NAME:
            p = self.project_pool[0]
            self._ensure_bucket_exists(settings.BUCKET_NAME, p["project_id"], p["credentials"], settings.REGION)

    def _ensure_bucket_exists(self, bucket_name, project_id, credentials, location):
        """Ensure GCS Bucket exists."""
        try:
            storage_client = storage.Client(credentials=credentials, project=project_id)
            bucket = storage_client.bucket(bucket_name)
            if not bucket.exists():
                logger.info(f"Bucket {bucket_name} not found. Creating in {location}...")
                bucket.create(location=location)
                logger.info(f"Bucket {bucket_name} created successfully.")
            else:
                logger.info(f"Bucket {bucket_name} already exists.")
        except Exception as e:
            logger.warning(f"Failed to ensure bucket {bucket_name} exists: {e}")

    def get_random_project(self) -> Optional[Dict]:
        if not self.project_pool:
            return None
        return random.choice(self.project_pool)

    def get_storage_client(self, project_id: Optional[str] = None) -> storage.Client:
        if not self.project_pool:
            raise RuntimeError("No active projects loaded, cannot create storage client.")

        target_project = self.get_project_by_id(project_id) if project_id else self.project_pool[0]
        if not target_project:
            raise RuntimeError(f"Project {project_id} not found, cannot create storage client.")

        target_project_id = target_project["project_id"]
        cached_client = self._storage_clients.get(target_project_id)
        if cached_client:
            return cached_client

        client = storage.Client(
            credentials=target_project["credentials"],
            project=target_project_id,
        )
        self._storage_clients[target_project_id] = client
        return client

    def get_project_by_id(self, project_id: Optional[str]) -> Optional[Dict]:
        return self.project_map.get(project_id)

config_manager = ConfigManager()
