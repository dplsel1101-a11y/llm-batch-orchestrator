import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Dict

import requests

from config.settings import settings


def run_command(command: str) -> int:
    print(f"\n$ {command}")
    completed = subprocess.run(
        command,
        shell=True,
        text=True,
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout.strip())
    if completed.stderr:
        print(completed.stderr.strip())
    return completed.returncode


def run_verify_script() -> int:
    print(f"\n$ {sys.executable} verify_v5.py")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "verify_v5.py"],
        text=True,
        capture_output=True,
        env=env,
    )
    if completed.stdout:
        print(completed.stdout.strip())
    if completed.stderr:
        print(completed.stderr.strip())
    return completed.returncode


def mask_value(raw_value: str) -> str:
    if not raw_value:
        return "<empty>"
    if len(raw_value) <= 8:
        return "***"
    return f"{raw_value[:4]}***{raw_value[-4:]}"


def print_runtime_config() -> None:
    config: Dict[str, str] = {
        "REGION": settings.REGION,
        "BUCKET_NAME": settings.BUCKET_NAME or "<empty>",
        "ACTIVE_KEY_GROUP": settings.ACTIVE_KEY_GROUP,
        "HTTPS_PROXY": mask_value(settings.HTTPS_PROXY or ""),
        "GOOGLE_APPLICATION_CREDENTIALS": settings.GOOGLE_APPLICATION_CREDENTIALS or "<empty>",
        "MODEL_ID": settings.MODEL_ID,
        "BATCH_ENABLED": str(settings.BATCH_ENABLED),
        "MAX_CONCURRENT_JOBS": str(settings.MAX_CONCURRENT_JOBS),
        "JOB_TIMEOUT_SECONDS": str(settings.JOB_TIMEOUT_SECONDS),
        "CHAT_RETRY_PER_PROJECT": str(settings.CHAT_RETRY_PER_PROJECT),
        "CHAT_BACKOFF_BASE_SECONDS": str(settings.CHAT_BACKOFF_BASE_SECONDS),
        "CHAT_BACKOFF_MAX_SECONDS": str(settings.CHAT_BACKOFF_MAX_SECONDS),
        "CHAT_BACKOFF_JITTER_SECONDS": str(settings.CHAT_BACKOFF_JITTER_SECONDS),
        "CHAT_MIN_INTERVAL_SECONDS": str(settings.CHAT_MIN_INTERVAL_SECONDS),
        "DATABASE_URL": settings.DATABASE_URL,
        "LOG_LEVEL": settings.LOG_LEVEL,
    }
    print("\n[CONFIG] Runtime settings")
    print(json.dumps(config, ensure_ascii=False, indent=2))


def check_key_layout() -> None:
    json_root = os.path.join(os.getcwd(), "json")
    group_dir = os.path.join(json_root, settings.ACTIVE_KEY_GROUP)

    root_files = []
    grouped_files = []
    if os.path.isdir(json_root):
        root_files = [f for f in os.listdir(json_root) if f.endswith(".json")]
    if os.path.isdir(group_dir):
        grouped_files = [f for f in os.listdir(group_dir) if f.endswith(".json")]

    print("\n[CHECK] Key layout")
    print(f"json root exists: {os.path.isdir(json_root)}")
    print(f"group dir exists: {os.path.isdir(group_dir)}")
    print(f"root json count: {len(root_files)}")
    print(f"group json count: {len(grouped_files)}")


def smoke_api() -> None:
    print("\n[CHECK] API smoke")
    db_file = os.path.join(os.getcwd(), ".fullcheck.db")
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///./.fullcheck.db"

    log_file = tempfile.NamedTemporaryFile(delete=False, suffix=".fullcheck.log")
    log_path = log_file.name
    log_file.close()
    log_handle = open(log_path, "w", encoding="utf-8")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8010",
        ],
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        health_ok = False
        for _ in range(40):
            time.sleep(1)
            if proc.poll() is not None:
                break
            try:
                response = requests.get("http://127.0.0.1:8010/health", timeout=5)
                if response.status_code == 200:
                    print(f"health: {response.status_code} {response.text}")
                    health_ok = True
                    break
            except requests.RequestException:
                continue

        if not health_ok:
            print("health: failed to reach endpoint")
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    output = f.read().strip()
                    if output:
                        print("startup logs:")
                        print(output[-2000:])
            return

        chat_response = requests.post(
            "http://127.0.0.1:8010/chat",
            json={"query": "ping", "use_search": False},
            timeout=20,
        )
        print(f"chat: {chat_response.status_code} {chat_response.text[:200]}")

        batch_response = requests.post(
            "http://127.0.0.1:8010/api/submit",
            json={"topic": "full-check"},
            timeout=10,
        )
        print(f"batch endpoint: {batch_response.status_code} {batch_response.text[:120]}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)

        log_handle.close()
        if os.path.exists(log_path):
            os.remove(log_path)

        if os.path.exists(db_file):
            os.remove(db_file)


def main() -> None:
    print("=== Full Project Check ===")
    run_command("python --version")
    run_command("git rev-parse --short HEAD")
    run_command("docker --version")
    run_command("docker compose version")

    print_runtime_config()
    check_key_layout()

    run_command("python -m compileall main.py config core services tests verify_v5.py full_check.py")
    run_command("python -m pip check")
    run_verify_script()
    run_command("docker compose config -q")

    smoke_api()
    print("\n=== Full Check Completed ===")


if __name__ == "__main__":
    main()
