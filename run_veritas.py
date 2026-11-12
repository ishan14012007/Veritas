"""
VERITAS Unified Platform Runner
Automatically activates both ACCORD (Conversational Agreements) and ARGUS (Fraud Interceptor)
on a single production-ready FastAPI gateway.
"""
import os
import sys

# Ensure UTF-8 console output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Load root .env environment variables
root_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(root_env):
    with open(root_env, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip("'\"")

# Ensure Veritas backend is on the Python path
veritas_backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Veritas", "backend")
if veritas_backend not in sys.path:
    sys.path.insert(0, veritas_backend)

from app.main import app
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print("=" * 70)
    print("[VERITAS] STARTING UNIFIED PLATFORM")
    print("   * Subsystem 1: ACCORD  (Conversational Ingestion & Expense Splits)")
    print("   * Subsystem 2: ARGUS   (Autonomous Pre-Settlement Fraud Interceptor)")
    print(f"   * Serving on:   http://0.0.0.0:{port}")
    print(f"   * ARGUS Portal: http://localhost:{port}/argus")
    print(f"   * API Docs:     http://localhost:{port}/docs")
    print("=" * 70)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
