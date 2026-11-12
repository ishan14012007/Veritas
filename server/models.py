from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class VerificationRequest(BaseModel):
    client_reference_id: Optional[str] = "EXT-REQ-001"
    paypal_merchant_id: Optional[str] = None
    brand_name: str
    merchant_url: str
    product_name: str
    price: float
    currency: str = "USD"

class WorkerResult(BaseModel):
    name: str
    status: str  # "PASS", "WARN", "FAIL"
    score: int   # 0 to 100
    latency_ms: float
    details: Dict[str, Any]

class TrustReport(BaseModel):
    brand_name: str
    merchant_url: str
    root_domain: str
    product_name: str
    price: float
    currency: str
    trust_score: int
    risk_level: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    action_taken: str # "APPROVED_FOR_CAPTURE" | "WARNED_REQUIRE_CONFIRMATION" | "TRANSACTION_VOIDED_AND_ACCOUNT_SEALED"
    merchant_status: str # "ACTIVE" | "FLAGGED_FOR_REVIEW" | "FROZEN_AND_QUARANTINED"
    cache_hit: bool = False
    cache_age_days: Optional[float] = None
    total_latency_ms: float
    workers: List[WorkerResult] = []
    evidence: List[str] = []
    ai_verdict_summary: str
    incident_reference_id: Optional[str] = None

class MerchantRecord(BaseModel):
    id: str
    paypal_merchant_id: str
    legal_business_name: str
    identity_status: str
    overall_reputation_score: int
    verified_at: Optional[str]
    created_at: str

class WebsiteRecord(BaseModel):
    id: str
    root_domain: str
    tld: str
    dns_hash: Optional[str]
    cert_fingerprint: Optional[str]
    has_mandatory_policies: bool
    catalog_depth: int
    status: str
    last_scraped_at: Optional[str]

class AssociationRecord(BaseModel):
    id: str
    merchant_id: str
    website_id: str
    brand_name_claimed: str
    association_status: str
    trust_score: int
    verified_at: Optional[str]
    expires_at: Optional[str]
    evidence_dossier: Optional[str]

class AuditLogEntry(BaseModel):
    id: str
    transaction_id: str
    brand_name: str
    target_url: str
    product_name: str
    price: str
    trust_score: int
    verdict: str
    merchant_state: str
    latency_ms: float
    timestamp: str

class AppealCreate(BaseModel):
    merchant_id: str
    incident_reference_id: str
    reason_category: str # "BRAND_MISMATCH", "DOCUMENT_VERIFICATION", "FALSE_POSITIVE"
    statement: str
    submitted_documents: Optional[List[str]] = []

class AppealResolution(BaseModel):
    ticket_id: str
    action: str # "APPROVE", "REJECT", "REQUEST_DOCS"
    resolution_notes: str

class AppealRecord(BaseModel):
    id: str
    merchant_id: str
    merchant_name: Optional[str] = None
    incident_reference_id: Optional[str] = None
    status: str
    reason_category: str
    statement: str
    submitted_documents: Optional[str]
    resolution_notes: Optional[str]
    created_at: str
    updated_at: str
