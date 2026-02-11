import os
import logging
import json
from google.oauth2 import service_account
from google.cloud import storage, aiplatform
from core.models import SessionLocal, Project, GoogleAccount
from config.settings import settings

logger = logging.getLogger(__name__)

class ConfigManager:
    _instance = None
    _active_project = None
    _storage_client = None
    _aiplatform_initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def get_active_project(self):
        """获取当前活跃项目配置，如果缓存为空则从 DB 加载"""
        if self._active_project:
            return self._active_project

        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.is_active == True).first()
            if project:
                # 预加载 account 以获取代理
                account = db.query(GoogleAccount).filter(GoogleAccount.id == project.google_account_id).first()
                self._active_project = {
                    "id": project.id,
                    "project_id": project.project_id,
                    "credentials_json": project.credentials_json,
                    "bucket_name": project.bucket_name,
                    "region": project.region,
                    "proxy_url": account.proxy_url if account else None
                }
                logger.info(f"Loaded active project: {project.project_name} ({project.project_id})")
                return self._active_project
            else:
                logger.warning("No active project found in database.")
                return None
        finally:
            db.close()

    def apply_proxy_settings(self):
        """应用代理设置到环境变量"""
        project_config = self.get_active_project()
        if not project_config:
            return

        proxy_url = project_config.get("proxy_url")
        if proxy_url:
            logger.info(f"Applying Proxy: {proxy_url}")
            os.environ["HTTPS_PROXY"] = proxy_url
            os.environ["HTTP_PROXY"] = proxy_url
            # gRPC 特有配置
            os.environ["GRPC_DNS_RESOLVER"] = "native"
            # os.environ["GRPC_PROXY_EXP"] = proxy_url # 注意：gRPC 代理支持可能需要特定库版本
        else:
            logger.info("No proxy configured for active account.")
            os.environ.pop("HTTPS_PROXY", None)
            os.environ.pop("HTTP_PROXY", None)

    def get_credentials(self):
        """从 JSON 内容构建凭证对象"""
        config = self.get_active_project()
        if not config:
            raise ValueError("No active project configured")
        
        info = json.loads(config["credentials_json"])
        return service_account.Credentials.from_service_account_info(info)

    def get_storage_client(self):
        """获取配置好的 Storage Client"""
        # 注意：Storage Client 通常不重用，或者需要小心处理。这里每次创建新的以确保凭证最新
        # 如果有性能问题再考虑缓存
        creds = self.get_credentials()
        project_id = self.get_active_project()["project_id"]
        return storage.Client(credentials=creds, project=project_id)

    def init_aiplatform(self):
        """初始化 Vertex AI"""
        config = self.get_active_project()
        if not config:
            raise ValueError("No active project context")
        
        creds = self.get_credentials()
        aiplatform.init(
            project=config["project_id"],
            location=config["region"],
            credentials=creds
        )
        logger.info(f"Vertex AI initialized for {config['project_id']} in {config['region']}")

    def reload_context(self):
        """强制刷新上下文 (切换项目时调用)"""
        logger.info("Reloading configuration context...")
        self._active_project = None
        self._storage_client = None
        
        self.apply_proxy_settings()
        try:
            self.init_aiplatform()
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI during reload: {e}")

# 单例导出
config_manager = ConfigManager()
