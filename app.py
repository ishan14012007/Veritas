import os
import sys

# Ensure workspace root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from server.database import init_db, get_db
from server.models import VerificationRequest, TrustReport, AppealCreate, AppealResolution
from server.registry import MerchantRegistry, seed_default_registry
from server.cache_manager import CacheManager
from argus.engine import ArgusEngine
from argus.paypal_gateway import PayPalGateway
from argus.appeals import AppealsManager

# Initialize Database on startup
init_db()

# Seed default verified merchants if empty
with get_db() as conn:
    count = conn.execute("SELECT count(*) FROM merchants;").fetchone()[0]
    if count == 0:
        seed_default_registry()

app = FastAPI(
    title="Argus & Shared Server Gateway",
    description="Merchant Verification, 7-Day Caching, Single-Flight Concurrency, and Real-Time PayPal Fraud Interception",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------
# 1. CORE VERIFICATION ENDPOINTS (Called by Frontends or Accord)
# -------------------------------------------------------------
@app.post("/api/v1/checkout/verify", response_model=TrustReport)
def verify_checkout_intent(req: VerificationRequest):
    """
    Main verification pipeline:
    - Resolves merchant & website identity in shared registry.
    - Evaluates 7-day conditional verification cache (<2ms).
    - If cache miss: coordinates single-flight parallel multi-worker engine.
    - Returns explainable TrustReport with 3-tier risk decision.
    """
    return ArgusEngine.verify_transaction(req)

# Backward compatibility endpoint for earlier tests
@app.post("/api/verify", response_model=TrustReport)
def verify_checkout_intent_legacy(req: VerificationRequest):
    return ArgusEngine.verify_transaction(req)

# -------------------------------------------------------------
# 2. PAYPAL ORDERS LIFECYCLE (Sandbox Integration)
# -------------------------------------------------------------
class OrderCreateReq(BaseModel):
    amount: float
    currency: str = "USD"
    brand_name: str = "Merchant"

class OrderActionReq(BaseModel):
    order_id: str
    merchant_id: Optional[str] = "MCH-DEFAULT"
    reason: Optional[str] = "PHISHING_DETECTED"

@app.get("/api/v1/paypal/config")
def get_paypal_config():
    creds = PayPalGateway.get_credentials()
    return {
        "client_id": creds["client_id"],
        "currency": "USD",
        "intent": "authorize",
        "mode": "sandbox",
        "configured": bool(creds["client_id"] and creds["client_secret"])
    }

@app.post("/api/v1/paypal/create-order")
def create_paypal_order(req: OrderCreateReq):
    return PayPalGateway.create_order(req.amount, req.currency, req.brand_name)

@app.post("/api/v1/paypal/authorize-order")
def authorize_paypal_order(req: OrderActionReq):
    return PayPalGateway.authorize_order(req.order_id)

@app.post("/api/v1/paypal/capture-order")
def capture_paypal_order(req: OrderActionReq):
    return PayPalGateway.capture_order(req.order_id)

@app.post("/api/v1/paypal/void-order")
def void_paypal_order(req: OrderActionReq):
    return PayPalGateway.void_order(req.order_id, req.merchant_id or "MCH-DEFAULT", req.reason or "SUSPICIOUS_ACTIVITY")

# -------------------------------------------------------------
# 3. GLOBAL MERCHANT TRUST REGISTRY (AG Grid Data Provider)
# -------------------------------------------------------------
@app.get("/api/v1/registry")
def get_merchant_registry():
    """Returns joined merchant-website records for AG Grid Registry table."""
    return MerchantRegistry.list_all_records()

@app.get("/api/v1/audit-log")
def get_audit_log(limit: int = 50):
    """Returns recent transaction audits for AG Grid Audit Log table."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs ORDER BY rowid DESC LIMIT ?;", (limit,))
        return [dict(r) for r in cursor.fetchall()]

# Legacy endpoint for frontend backwards-compat
@app.get("/api/audit-log")
def get_audit_log_legacy():
    return get_audit_log()

# -------------------------------------------------------------
# 4. MERCHANT GRIEVANCE & APPEAL RESOLUTION
# -------------------------------------------------------------
@app.get("/api/v1/appeals")
def get_appeals():
    """Returns all appeal tickets for AG Grid Appeals Center."""
    return AppealsManager.list_appeals()

@app.post("/api/v1/appeals/submit")
def submit_appeal(req: AppealCreate):
    """Allows a restricted merchant to submit evidence and challenge an automated freeze."""
    return AppealsManager.create_appeal(req)

@app.post("/api/v1/appeals/resolve")
def resolve_appeal(req: AppealResolution):
    """Admin action to approve/reject an appeal, restoring merchant access live."""
    try:
        return AppealsManager.resolve_appeal(req)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# -------------------------------------------------------------
# 5. CACHE MANAGEMENT & CHANGE DETECTION HOOK
# -------------------------------------------------------------
class InvalidationReq(BaseModel):
    merchant_id: str
    website_id: str
    reason: str = "MANUAL_CHANGE_DETECTED"

@app.post("/api/v1/cache/invalidate")
def invalidate_cache(req: InvalidationReq):
    CacheManager.invalidate(req.merchant_id, req.website_id, req.reason)
    return {"status": "SUCCESS", "message": f"Cache invalidated for merchant {req.merchant_id}"}

# -------------------------------------------------------------
# 6. RENDER CLOUD HEALTH CHECK & POSTMAN DOWNLOADS
# -------------------------------------------------------------
from fastapi.responses import FileResponse

@app.get("/api/v1/health")
def health_check():
    return {
        "status": "HEALTHY",
        "service": "Argus Fraud Interceptor",
        "engine": "Parallel Multi-Worker Matrix",
        "database": "SQLite WAL",
        "timestamp": os.path.exists("argus.db")
    }

@app.get("/api/v1/postman/collection")
def download_postman_collection():
    collection_path = os.path.join(BASE_DIR, "postman", "argus_api_collection.json")
    if os.path.exists(collection_path):
        return FileResponse(collection_path, media_type="application/json", filename="argus_api_collection.json")
    raise HTTPException(status_code=404, detail="Postman collection file not found")

@app.get("/api/v1/postman/environment")
def download_postman_environment():
    env_path = os.path.join(BASE_DIR, "postman", "argus_environment.json")
    if os.path.exists(env_path):
        return FileResponse(env_path, media_type="application/json", filename="argus_environment.json")
    raise HTTPException(status_code=404, detail="Postman environment file not found")

# Serve frontend static assets
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    veritas_backend = os.path.join(BASE_DIR, "Veritas", "backend")
    if os.path.exists(veritas_backend):
        if veritas_backend not in sys.path:
            sys.path.insert(0, veritas_backend)
        from app.main import app as unified_app
        print("=" * 70)
        print("[VERITAS] STARTING UNIFIED PLATFORM")
        print("   * Subsystem 1: ACCORD  (Conversational Ingestion & Expense Splits)")
        print("   * Subsystem 2: ARGUS   (Autonomous Pre-Settlement Fraud Interceptor)")
        print(f"   * Serving on:   http://0.0.0.0:{port}")
        print(f"   * ARGUS Portal: http://localhost:{port}/argus")
        print(f"   * API Docs:     http://localhost:{port}/docs")
        print("=" * 70)
        uvicorn.run(unified_app, host="0.0.0.0", port=port, reload=False)
    else:
        uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
