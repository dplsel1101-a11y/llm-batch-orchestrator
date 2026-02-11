from sqlalchemy import Column, String, Integer, DateTime, Text, create_engine, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime
from config.settings import settings

Base = declarative_base()

class GoogleAccount(Base):
    """Google 账号 (代理分组)"""
    __tablename__ = "google_accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_name = Column(String(100), unique=True, nullable=False)
    proxy_url = Column(String(255), nullable=True)  # socks5://...
    created_at = Column(DateTime, default=datetime.utcnow)

    projects = relationship("Project", back_populates="account")

class Project(Base):
    """GCP 项目配置"""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    google_account_id = Column(Integer, ForeignKey("google_accounts.id"))
    project_name = Column(String(100))
    project_id = Column(String(100), unique=True, nullable=False)
    credentials_json = Column(Text, nullable=False)
    bucket_name = Column(String(100), nullable=False)
    region = Column(String(50), default="global")
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("GoogleAccount", back_populates="projects")
    jobs = relationship("BatchJob", back_populates="project")

class BatchJob(Base):
    __tablename__ = "batch_jobs"

    job_uuid = Column(String(64), primary_key=True)
    current_stage = Column(Integer, default=0)
    vertex_job_name = Column(String(255), nullable=True)
    status = Column(String(20), default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED
    gcs_prefix = Column(String(255))
    
    # 增强字段
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_error = Column(Text, nullable=True)

    # 关联项目
    project_id_fk = Column(Integer, ForeignKey("projects.id"), nullable=True)
    project = relationship("Project", back_populates="jobs")

# DB 初始化
engine = create_engine(
    settings.DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
