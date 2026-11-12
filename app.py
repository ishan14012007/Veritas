"""
VERITAS Unified Platform - Production Gateway Entrypoint
Runs both ACCORD (Conversational Ingestion & Consensus) and ARGUS (Fraud Interceptor)
along with the compiled React Frontend.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
veritas_backend = os.path.join(BASE_DIR, "Veritas", "backend")
backend_app_dir = os.path.join(veritas_backend, "app")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if veritas_backend not in sys.path:
    sys.path.insert(0, veritas_backend)

# Turn this module into a package pointing to Veritas/backend/app
__path__ = [backend_app_dir]

# Load root .env environment variables if present
root_env = os.path.join(BASE_DIR, ".env")
if os.path.exists(root_env):
    with open(root_env, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

from app.main import app as _fastapi_app

app = _fastapi_app

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
