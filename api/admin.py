from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import json

from core.models import SessionLocal, GoogleAccount, Project
from config.manager import config_manager

router = APIRouter(prefix="/admin", tags=["Admin"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Models ---
class AccountCreate(BaseModel):
    account_name: str
    proxy_url: Optional[str] = None

class AccountResponse(AccountCreate):
    id: int
    class Config:
        orm_mode = True

class ProjectCreate(BaseModel):
    google_account_id: int
    project_name: str
    region: str = "global"

class ProjectResponse(ProjectCreate):
    id: int
    project_id: str
    is_active: bool
    class Config:
        orm_mode = True

# --- API Endpoints ---

@router.get("/accounts", response_model=List[AccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    """列出所有账号"""
    return db.query(GoogleAccount).all()

@router.post("/accounts", response_model=AccountResponse)
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    """创建新账号 (代理分组)"""
    db_account = GoogleAccount(account_name=account.account_name, proxy_url=account.proxy_url)
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

@router.get("/accounts/{account_id}/projects", response_model=List[ProjectResponse])
def list_projects(account_id: int, db: Session = Depends(get_db)):
    """列出指定账号下的项目"""
    return db.query(Project).filter(Project.google_account_id == account_id).all()

@router.post("/accounts/{account_id}/projects")
def add_project(
    account_id: int, 
    project_name: str,
    bucket_name: str,
    region: str = "global",
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    """上传 credentials.json 并创建项目"""
    content = file.file.read()
    try:
        data = json.loads(content)
        project_id = data.get("project_id")
        if not project_id:
            raise HTTPException(status_code=400, detail="Invalid JSON: missing project_id")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    # Check existence
    if db.query(Project).filter(Project.project_id == project_id).first():
        raise HTTPException(status_code=400, detail="Project already exists")

    new_project = Project(
        google_account_id=account_id,
        project_name=project_name,
        project_id=project_id,
        credentials_json=content.decode("utf-8"),
        bucket_name=bucket_name,
        region=region,
        is_active=False
    )
    db.add(new_project)
    db.commit()
    return {"status": "ok", "project_id": project_id}

@router.post("/projects/{project_id}/activate")
def activate_project(project_id: int, db: Session = Depends(get_db)):
    """激活项目 (单活跃模式)"""
    # 1. 事务：全部设为 False
    db.query(Project).update({Project.is_active: False})
    
    # 2. 设置目标为 True
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project.is_active = True
    db.commit()
    
    # 3. 触发系统上下文重载
    config_manager.reload_context()
    
    return {"status": "activated", "project": project.project_name}

@router.get("/status")
def get_status():
    """获取当前活跃配置状态"""
    active = config_manager.get_active_project()
    if not active:
        return {"active": False}
    
    return {
        "active": True,
        "project_id": active["project_id"],
        "region": active["region"],
        "proxy_url": active["proxy_url"] or "None"
    }
