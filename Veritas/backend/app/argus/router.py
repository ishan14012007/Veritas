import os
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.argus.models import VerificationRequest, TrustReport, AppealCreate, AppealResolution
from app.argus.engine import ArgusEngine
from app.argus.registry import MerchantRegistry
from app.argus.database import get_db, init_db
from app.argus.appeals import AppealsManager
from app.argus.paypal_gateway import PayPalGateway
from app.argus.cache_manager import CacheManager
from fastapi.responses import FileResponse

router = APIRouter(tags=["ARGUS Fraud Interceptor"])

# Initialize DB on module import
init_db()

class OrderCreateReq(BaseModel):
    amount: float
    currency: str = "USD"
    brand_name: str = "Merchant"

class OrderActionReq(BaseModel):
    order_id: str
    merchant_id: Optional[str] = "MCH-DEFAULT"
    reason: Optional[str] = "PHISHING_DETECTED"

# -------------------------------------------------------------
# 1. CORE VERIFICATION ENDPOINTS
# -------------------------------------------------------------
@router.post("/verify", response_model=TrustReport, summary="Verify checkout intent")
@router.post("/checkout/verify", response_model=TrustReport, summary="Verify checkout intent (alias)")
def verify_checkout_intent(req: VerificationRequest):
    """
    Main Argus verification pipeline:
    - Resolves merchant & website identity in shared registry.
    - Evaluates 7-day conditional verification cache (<2ms).
    - If cache miss: coordinates single-flight parallel multi-worker engine.
    - Returns explainable TrustReport with 3-tier risk decision.
    """
    return ArgusEngine.verify_transaction(req)

# -------------------------------------------------------------
# 2. PAYPAL ORDERS LIFECYCLE (Sandbox Integration)
# -------------------------------------------------------------
@router.get("/paypal/config")
def get_paypal_config():
    """Returns public PayPal Client ID for the JavaScript SDK."""
    creds = PayPalGateway.get_credentials()
    return {
        "client_id": creds["client_id"],
        "base_url": creds["base_url"],
        "merchant_id": creds.get("merchant_id", "2252PMF2CJ7Q2"),
        "currency": "USD",
        "intent": "AUTHORIZE"
    }

@router.post("/paypal/create-order")
def create_paypal_order(req: OrderCreateReq):
    """Creates a real pre-settlement authorization order in PayPal Sandbox."""
    return PayPalGateway.create_order(
        amount=req.amount,
        currency=req.currency,
        brand_name=req.brand_name,
        intent="AUTHORIZE",
    )

@router.post("/paypal/authorize-order")
def authorize_paypal_order(req: OrderActionReq):
    """Authorizes an order to place a pre-settlement hold on funds."""
    return PayPalGateway.authorize_order(req.order_id)

@router.post("/paypal/capture-order")
def capture_paypal_order(req: OrderActionReq):
    """Captures funds after Argus verifies the merchant as genuine."""
    return PayPalGateway.capture_order(req.order_id)

@router.post("/paypal/void-order")
def void_paypal_order(req: OrderActionReq):
    """Voids authorization hold immediately when fraud is intercepted."""
    return PayPalGateway.void_order(
        order_id=req.order_id,
        merchant_id=req.merchant_id or "MCH-SCAMMER",
        reason=req.reason or "MALICIOUS_IMPERSONATION"
    )

# -------------------------------------------------------------
# 3. GLOBAL MERCHANT TRUST REGISTRY & AUDIT LOGS (AG Grid)
# -------------------------------------------------------------
@router.get("/registry")
def get_merchant_registry():
    """Returns joined merchant-website records for AG Grid Registry table."""
    return MerchantRegistry.list_all_records()

@router.get("/audit-log")
def get_audit_log(limit: int = 50):
    """Returns recent transaction audits for AG Grid Audit Log table."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs ORDER BY rowid DESC LIMIT ?;", (limit,))
        return [dict(r) for r in cursor.fetchall()]

# -------------------------------------------------------------
# 4. MERCHANT GRIEVANCE & APPEALS RESOLUTION
# -------------------------------------------------------------
@router.get("/appeals")
def get_appeals():
    """Returns all appeal tickets for AG Grid Appeals Center."""
    return AppealsManager.list_appeals()

@router.post("/appeals")
@router.post("/appeals/submit")
def create_appeal(req: AppealCreate):
    """Allows merchants to dispute a false-positive flag and submit evidence."""
    return AppealsManager.create_appeal(req)

@router.post("/appeals/resolve")
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

@router.post("/cache/invalidate")
def invalidate_cache(req: InvalidationReq):
    CacheManager.invalidate(req.merchant_id, req.website_id, req.reason)
    return {"status": "SUCCESS", "message": f"Cache invalidated for merchant {req.merchant_id}"}

# -------------------------------------------------------------
# 6. HEALTH & SPONSOR EXPORTS
# -------------------------------------------------------------
@router.get("/health")
def argus_health():
    return {
        "status": "HEALTHY",
        "service": "Argus Fraud Interceptor",
        "engine": "Parallel Multi-Worker Matrix",
        "database": "SQLite WAL",
        "subsystem": "VERITAS.ARGUS",
        "active": True
    }

@router.get("/postman/collection")
def download_postman_collection():
    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    collection_path = os.path.join(workspace_root, "postman", "argus_api_collection.json")
    if os.path.exists(collection_path):
        return FileResponse(collection_path, media_type="application/json", filename="argus_api_collection.json")
    raise HTTPException(status_code=404, detail="Postman collection file not found")

@router.get("/postman/environment")
def download_postman_environment():
    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    env_path = os.path.join(workspace_root, "postman", "argus_environment.json")
    if os.path.exists(env_path):
        return FileResponse(env_path, media_type="application/json", filename="argus_environment.json")
    raise HTTPException(status_code=404, detail="Postman environment file not found")
