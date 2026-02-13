import os
import logging
from sqlalchemy import Column, String, Integer, DateTime, Text, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
from config.settings import settings

Base = declarative_base()
logger = logging.getLogger(__name__)


def _prepare_sqlite_directory(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    sqlite_path = database_url.replace("sqlite:///", "", 1)
    if not sqlite_path or sqlite_path == ":memory:":
        return

    db_dir = os.path.dirname(sqlite_path)
    if not db_dir:
        return

    try:
        os.makedirs(db_dir, exist_ok=True)
    except OSError as exc:
        logger.warning(f"Failed to prepare sqlite directory {db_dir}: {exc}")

class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id = Column(String, primary_key=True, index=True)
    status = Column(String, default="PENDING", index=True)  # PENDING, SUBMITTED, RUNNING, SUCCEEDED, FAILED
    
    # Job Details
    input_gcs_uri = Column(String)
    output_gcs_uri = Column(String)
    vertex_job_id = Column(String, nullable=True) # Resource Name
    
    # Scheduling & Result
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    result_summary = Column(Text, nullable=True)
    
    # Reliability
    retry_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    # Routing Trace
    used_project_id = Column(String, nullable=True) # Which Project ID handled this job

    def __repr__(self):
        return f"<BatchJob(id={self.id}, status={self.status}, project={self.used_project_id})>"

# DB Init
_prepare_sqlite_directory(settings.DATABASE_URL)
engine = create_engine(
    settings.DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_batch_jobs_status ON batch_jobs (status)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_batch_jobs_updated_at ON batch_jobs (updated_at)"
            )
