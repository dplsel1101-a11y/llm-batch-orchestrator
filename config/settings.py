import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 强制加载 .env，覆盖系统变量
load_dotenv(override=True)

class Settings(BaseSettings):
    # 基础 GCP 配置
    PROJECT_ID: str
    REGION: str = "us-central1"
    BUCKET_NAME: str
    GOOGLE_APPLICATION_CREDENTIALS: str

    # 模型与任务配置
    MODEL_ID: str = "publishers/google/models/gemini-3-flash-preview"
    MAX_CONCURRENT_JOBS: int = 5
    JOB_TIMEOUT_SECONDS: int = 7200  # 2小时超时熔断
    
    # 数据库 (默认本地 SQLite)
    DATABASE_URL: str = "sqlite:///./local_jobs.db"
    
    # 日志
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"  # 忽略多余的环境变量

settings = Settings()
