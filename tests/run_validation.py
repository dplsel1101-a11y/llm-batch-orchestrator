import sys
import os
import time
import requests
import json
from google.cloud import storage
from dotenv import load_dotenv

# 1. 环境加载
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

API_URL = "http://127.0.0.1:8000"
BUCKET_NAME = os.getenv("BUCKET_NAME")
CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# 颜色输出
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

def log(msg, status="INFO"):
    if status == "PASS":
        print(f"{Colors.OKGREEN}[PASS] {msg}{Colors.ENDC}")
    elif status == "FAIL":
        print(f"{Colors.FAIL}[FAIL] {msg}{Colors.ENDC}")
    elif status == "WARN":
        print(f"{Colors.WARNING}[WARN] {msg}{Colors.ENDC}")
    else:
        print(f"[INFO] {msg}")

def step_1_check_gcp_auth():
    log("Step 1: Checking GCP Permissions...")
    if not os.path.exists(f"../{CREDENTIALS}") and not os.path.exists(CREDENTIALS):
        # Try absolute path or relative to script
        if os.path.exists(os.path.join(os.path.dirname(__file__), "../gcp-key.json")):
             pass # confirm it exists
        else:
            log(f"Key file not found at {CREDENTIALS}", "FAIL")
            return False
    
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob("tests/connection_check.txt")
        blob.upload_from_string("Connection OK")
        log(f"Successfully wrote to gs://{BUCKET_NAME}/tests/connection_check.txt", "PASS")
        return True
    except Exception as e:
        log(f"GCP Auth Failed: {e}", "FAIL")
        return False

def step_2_check_api_health():
    log("Step 2: Checking API Health...")
    try:
        res = requests.get(f"{API_URL}/health")
        if res.status_code == 200:
            log("API is healthy", "PASS")
            return True
        else:
            log(f"API returned {res.status_code}", "FAIL")
            return False
    except requests.exceptions.ConnectionError:
        log("Cannot connect to API. Is 'uvicorn main:app' running?", "FAIL")
        return False

def step_3_submit_job():
    log("Step 3: Submitting Test Job...")
    payload = {"topic": "Automated Test: Future of AI"}
    try:
        res = requests.post(f"{API_URL}/api/submit", json=payload)
        if res.status_code == 200:
            data = res.json()
            job_uuid = data.get("job_uuid")
            log(f"Job Submitted. UUID: {job_uuid}", "PASS")
            return job_uuid
        else:
            log(f"Submission failed: {res.text}", "FAIL")
            return None
    except Exception as e:
        log(f"Request failed: {e}", "FAIL")
        return None

def step_4_verify_gcs_artifacts(job_uuid):
    log(f"Step 4: Verifying GCS Artifacts for {job_uuid}...")
    # 给一点时间让文件上传完成
    time.sleep(2)
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        # 检查 Stage 1 Input 是否存在
        blob_path = f"{job_uuid}/stage_1/input.jsonl"
        blob = bucket.blob(blob_path)
        
        if blob.exists():
            content = blob.download_as_text()
            if "custom_id" in content and "request" in content:
                log(f"Found valid input.jsonl at {blob_path}", "PASS")
                return True
            else:
                log(f"File exists but content format is wrong: {content[:50]}...", "FAIL")
                return False
        else:
            log(f"File not found: {blob_path}", "FAIL")
            return False
    except Exception as e:
        log(f"Verification failed: {e}", "FAIL")
        return False

def step_5_monitor_status(job_uuid):
    log(f"Step 5: Monitoring Job Status (10s check)...")
    for i in range(5):
        res = requests.get(f"{API_URL}/api/jobs/{job_uuid}")
        data = res.json()
        status = data.get("status")
        stage = data.get("current_stage")
        log(f"Poll {i+1}: Status={status}, Stage={stage}")
        
        if status == "FAILED":
            log(f"Job Failed! Error: {data.get('last_error')}", "FAIL")
            return
        if status == "RUNNING" and stage >= 1:
            log("Job successfully entered RUNNING state on Vertex AI", "PASS")
            return
        
        time.sleep(2)
    
    log("Job is still PENDING after 10s (This might be normal for cold start)", "WARN")

if __name__ == "__main__":
    print("=== STARTING VALIDATION SUITE ===")
    
    # Check credentials
    if not step_1_check_gcp_auth():
        print("Skipping further tests due to Auth failure.")
        sys.exit(1)
        
    if not step_2_check_api_health():
        print("Skipping further tests due to API failure.")
        sys.exit(1)
        
    uuid = step_3_submit_job()
    if uuid:
        if step_4_verify_gcs_artifacts(uuid):
            step_5_monitor_status(uuid)
    
    print("\n=== TEST COMPLETE ===")
