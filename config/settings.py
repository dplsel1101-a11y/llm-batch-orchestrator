import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 强制加载 .env，覆盖系统变量
load_dotenv(override=True)

class Settings(BaseSettings):
    # 基础 GCP 配置
    # 基础 GCP 配置 (现在由 ConfigManager 动态管理，这里设为可选以通过启动检查)
    # 基础 GCP 配置
    # PROJECT_ID/BUCKET_NAME now managed or verification-only here
    REGION: str = "global"
    BUCKET_NAME: str = "" # Required from .env
    
    # 代理与密钥分组
    # ACTIVE_KEY_GROUP defaults to "001" if not set in env
    HTTPS_PROXY: Optional[str] = None
    ACTIVE_KEY_GROUP: str = "001"
    
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # 模型与任务配置
    MODEL_ID: str = "gemini-3-flash-preview"
    MAX_CONCURRENT_JOBS: int = 5
    JOB_TIMEOUT_SECONDS: int = 7200  # 2小时超时熔断
    
    # 数据库 (Moved to /app/data to avoid mount conflicts)
    DATABASE_URL: str = "sqlite:////app/data/batch_jobs.db"
    
    # 日志
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"  # 忽略多余的环境变量

settings = Settings()
