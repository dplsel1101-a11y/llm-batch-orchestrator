import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 强制加载 .env，覆盖系统变量
load_dotenv(override=True)


def _default_database_url() -> str:
    if os.path.exists("/.dockerenv"):
        return "sqlite:////app/data/batch_jobs.db"
    return "sqlite:///./local_jobs.db"

class Settings(BaseSettings):
    # 基础 GCP 配置
    # 基础 GCP 配置 (现在由 ConfigManager 动态管理，这里设为可选以通过启动检查)
    # 基础 GCP 配置
    # PROJECT_ID/BUCKET_NAME now managed or verification-only here
    REGION: str = "global"
    BUCKET_NAME: str = ""  # Needed only when BATCH_ENABLED=true
    
    # 代理与密钥分组
    # ACTIVE_KEY_GROUP supports: single group ("001"), multiple ("001,002"), all ("all")
    HTTPS_PROXY: Optional[str] = None
    ACTIVE_KEY_GROUP: str = "001"
    
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # 模型与任务配置
    MODEL_ID: str = "gemini-3-flash-preview"
    BATCH_ENABLED: bool = False
    MAX_CONCURRENT_JOBS: int = 5
    JOB_TIMEOUT_SECONDS: int = 7200  # 2小时超时熔断

    # Chat Routing / Retry
    CHAT_RETRY_PER_PROJECT: int = 3
    CHAT_BACKOFF_BASE_SECONDS: float = 0.8
    CHAT_BACKOFF_MAX_SECONDS: float = 8.0
    CHAT_BACKOFF_JITTER_SECONDS: float = 0.4
    CHAT_MIN_INTERVAL_SECONDS: float = 0.2
    
    # 数据库
    DATABASE_URL: str = _default_database_url()
    
    # 日志
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"  # 忽略多余的环境变量

settings = Settings()
