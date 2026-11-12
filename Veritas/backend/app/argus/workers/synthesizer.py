import time
import uuid
from typing import Dict, Any, List
from app.argus.models import WorkerResult

def synthesize_verdict(
    brand: str,
    url: str,
    product: str,
    price: float,
    w1: WorkerResult,
    w2: WorkerResult,
    w3: WorkerResult
) -> Dict[str, Any]:
    start = time.perf_counter()
    
    # Weighted composite score
    composite = int(
        (w1.score * 0.40) +
        (w2.score * 0.35) +
        (w3.score * 0.25)
    )
    
    evidence: List[str] = []
    incident_id = None
    
    # Check Worker 1 (Domain Forensics)
    if w1.details.get("official_domain_match"):
        evidence.append(f"Domain verified: '{w1.details.get('root_domain')}' is officially registered to {brand}.")
    elif w1.details.get("is_typosquatting") or w1.score < 50:
        evidence.append(f"CRITICAL: Claimed brand '{brand}' does not match root domain '{w1.details.get('root_domain')}'. Detected typosquatting / brand spoofing.")
        
    if w1.details.get("is_suspicious_tld"):
        evidence.append(f"Merchant is operating on high-risk TLD '{w1.details.get('tld')}' commonly linked with disposable phishing.")
        
    # Check Worker 2 (Web Inspector)
    if w2.details.get("single_page_scam_risk"):
        evidence.append("Page inspection revealed a single-product landing page with no verifiable customer refund policy or corporate address.")
    elif w2.details.get("has_mandatory_policies"):
        evidence.append("Mandatory consumer protection policies (Terms, Privacy, Refund) verified active.")
        
    # Check Worker 3 (Price Anomaly)
    if w3.details.get("anomaly_detected"):
        evidence.append(f"Pricing anomaly: Listed price of {price} is over 80% below standard market MSRP for '{product}'.")

    # 3-Tier Risk Hierarchy
    if composite >= 70 and not w1.details.get("is_typosquatting"):
        risk_level = "LOW"
        action = "APPROVED_FOR_CAPTURE"
        merchant_status = "ACTIVE"
        verdict = f"Verified Merchant. Identity, domain authenticity, and catalog checks passed for '{brand}'. Safe for PayPal checkout."
    elif composite >= 45 and not w1.details.get("is_typosquatting"):
        risk_level = "MEDIUM"
        action = "WARNED_REQUIRE_CONFIRMATION"
        merchant_status = "FLAGGED_FOR_REVIEW"
        incident_id = f"INC-WARN-{uuid.uuid4().hex[:6].upper()}"
        verdict = f"Moderate Risk Detected for '{brand}'. Domain is unestablished or policies are incomplete. Step-up buyer confirmation advised."
    else:
        risk_level = "CRITICAL" if composite < 30 else "HIGH"
        action = "TRANSACTION_VOIDED_AND_ACCOUNT_SEALED"
        merchant_status = "FROZEN_AND_QUARANTINED"
        incident_id = f"INC-SEAL-{uuid.uuid4().hex[:6].upper()}"
        verdict = f"Phishing & Brand Impersonation Intercepted! Merchant '{url}' was caught falsely declaring brand '{brand}'. Transaction voided before capture; merchant account has been quarantined."

    latency = round((time.perf_counter() - start) * 1000, 2)
    return {
        "trust_score": composite,
        "risk_level": risk_level,
        "action": action,
        "merchant_status": merchant_status,
        "evidence": evidence,
        "verdict": verdict,
        "incident_reference_id": incident_id,
        "latency_ms": latency
    }
