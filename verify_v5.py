import os
import sys
import logging
import requests
from collections import Counter
from config.manager import config_manager
from config.settings import settings

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("verify_v5")

def check_proxy():
    print("\n--- 1. Proxy Verification ---")
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    print(f"Configured Proxy: {proxy}")
    
    if not proxy:
        print("[INFO] No proxy configured (direct connect).")
        return

    if "username:password" in proxy or "ip:port" in proxy:
         print("[ERROR] You are using the default placeholder 'username:password@ip:port'.")
         print("   Please restart the container with your ACTUAL proxy credentials in the -e HTTPS_PROXY command.")
         return
    
    try:
        print("Attempting to fetch external IP via Proxy...")
        # timeout set to 10s to fail fast if proxy is bad
        response = requests.get("https://api.ipify.org?format=json", timeout=10)
        data = response.json()
        print(f"[OK] External IP: {data['ip']}")
        print("(Please verify this matches your Proxy IP)")
    except Exception as e:
        print(f"[ERROR] Proxy Test Failed: {e}")
        if "Missing dependencies for SOCKS support" in str(e):
             print("   (Ensure pysocks is installed via requirements.txt)")

def check_keys():
    print("\n--- 2. Key Loading Verification ---")
    pool = config_manager.project_pool
    print(f"Active Key Group: {settings.ACTIVE_KEY_GROUP}")
    print(f"Loaded Projects Count: {len(pool)}")
    
    if not pool:
        print("[ERROR] No keys loaded! Check json/ directory.")
        return

    for p in pool:
        project_id = p.get("project_id") if isinstance(p, dict) else None
        print(f" - Loaded: {project_id}")

def check_randomization():
    print("\n--- 3. Random Dispatch Verification (Simulation) ---")
    pool = config_manager.project_pool
    if not pool:
        print("Skipping randomization test (no keys).")
        return

    print("Simulating 20 project selections...")
    results = []
    for _ in range(20):
        proj = config_manager.get_random_project()
        if not isinstance(proj, dict):
            continue
        project_id = proj.get("project_id")
        if project_id:
            results.append(project_id)

    if not results:
        print("[WARN] No project selected during simulation.")
        return
    
    counts = Counter(results)
    for pid, count in counts.items():
        print(f" - Project {pid}: selected {count} times")
    
    if len(counts) > 1:
        print("[OK] Randomization is working (multiple projects selected).")
    else:
        print("[WARN] Only one project selected (could be chance if pool is key small, or logic error).")

if __name__ == "__main__":
    print("=== Accessing Headless Orchestrator Verification (v5) ===")
    
    # Check 1: Keys (Loaded by ConfigManager init)
    check_keys()
    
    # Check 2: Proxy
    check_proxy()
    
    # Check 3: Logic
    check_randomization()
    print("\n=== Verification Complete ===\n")
