import time
import uuid
import concurrent.futures
from typing import Dict, Any, Tuple
from server.models import VerificationRequest, TrustReport, WorkerResult
from server.registry import MerchantRegistry
from server.cache_manager import CacheManager
from server.single_flight import SINGLE_FLIGHT
from server.database import get_db
from argus.workers.domain_forensics import run_domain_forensics, extract_root_domain_and_tld
from argus.workers.web_inspector import run_web_inspector
from argus.workers.price_anomaly import run_price_anomaly
from argus.workers.synthesizer import synthesize_verdict

def _execute_deep_inspection(req: VerificationRequest) -> Tuple[Dict[str, Any], list]:
    """Runs the 3 parallel workers and synthesizes findings."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(run_domain_forensics, req.brand_name, req.merchant_url)
        f2 = executor.submit(run_web_inspector, req.merchant_url)
        f3 = executor.submit(run_price_anomaly, req.product_name, req.price, req.brand_name)
        
        w1: WorkerResult = f1.result()
        w2: WorkerResult = f2.result()
        w3: WorkerResult = f3.result()
        
    synthesis = synthesize_verdict(req.brand_name, req.merchant_url, req.product_name, req.price, w1, w2, w3)
    return synthesis, [w1, w2, w3]

class ArgusEngine:
    @staticmethod
    def verify_transaction(req: VerificationRequest) -> TrustReport:
        master_start = time.perf_counter()
        root_domain, tld = extract_root_domain_and_tld(req.merchant_url)
        
        # 1. Resolve or create entities in the shared registry
        paypal_id = req.paypal_merchant_id or f"P-MCH-{root_domain.replace('.', '').upper()[:8]}"
        merchant = MerchantRegistry.get_or_create_merchant(paypal_id, req.brand_name)
        website = MerchantRegistry.get_or_create_website(root_domain, tld)
        
        # 2. Check 7-Day Conditional Verification Cache
        association = MerchantRegistry.get_association(merchant["id"], website["id"])
        is_cached, age_days, cached_data = CacheManager.evaluate_cache(association)
        
        total_latency = 0.0
        
        if is_cached and cached_data:
            total_latency = round((time.perf_counter() - master_start) * 1000, 2)
            report = TrustReport(
                brand_name=req.brand_name,
                merchant_url=req.merchant_url,
                root_domain=root_domain,
                product_name=req.product_name,
                price=req.price,
                currency=req.currency,
                trust_score=cached_data["trust_score"],
                risk_level="LOW",
                action_taken="APPROVED_FOR_CAPTURE",
                merchant_status="ACTIVE",
                cache_hit=True,
                cache_age_days=age_days,
                total_latency_ms=total_latency,
                workers=[],
                evidence=cached_data["evidence"],
                ai_verdict_summary=f"Fast-Path Verification Reused. Domain '{root_domain}' was verified {age_days} days ago with active 7-day trust cache.",
                incident_reference_id=None
            )
        else:
            # 3. Cache Miss / Invalidation: Execute Deep Verification via Single-Flight Concurrency
            # Keyed on root_domain to prevent thundering herd crawls
            flight_res, subscribers = SINGLE_FLIGHT.execute(root_domain, _execute_deep_inspection, req)
            synthesis, workers = flight_res
            
            total_latency = round((time.perf_counter() - master_start) * 1000, 2)
            
            # 4. Update the Registry & 7-Day Cache
            is_approved = (synthesis["action"] == "APPROVED_FOR_CAPTURE")
            verified_at_iso, expires_at_iso = CacheManager.compute_expiry(days=7)
            
            assoc_status = "AUTHORIZED" if is_approved else ("UNVERIFIED" if synthesis["risk_level"] == "MEDIUM" else "REVOKED")
            m_status = synthesis["merchant_status"]
            
            MerchantRegistry.upsert_association(
                merchant_id=merchant["id"],
                website_id=website["id"],
                brand_name_claimed=req.brand_name,
                association_status=assoc_status,
                trust_score=synthesis["trust_score"],
                verified_at=verified_at_iso if is_approved else None,
                expires_at=expires_at_iso if is_approved else None,
                evidence_dossier=synthesis["evidence"]
            )
            
            MerchantRegistry.update_merchant_status(merchant["id"], m_status, synthesis["trust_score"])
            
            report = TrustReport(
                brand_name=req.brand_name,
                merchant_url=req.merchant_url,
                root_domain=root_domain,
                product_name=req.product_name,
                price=req.price,
                currency=req.currency,
                trust_score=synthesis["trust_score"],
                risk_level=synthesis["risk_level"],
                action_taken=synthesis["action"],
                merchant_status=synthesis["merchant_status"],
                cache_hit=False,
                cache_age_days=0.0,
                total_latency_ms=total_latency,
                workers=workers,
                evidence=synthesis["evidence"],
                ai_verdict_summary=synthesis["verdict"],
                incident_reference_id=synthesis["incident_reference_id"]
            )
            
        # 5. Record into the Audit Log
        ArgusEngine._log_audit(merchant["id"], website["id"], req, report)
        return report

    @staticmethod
    def _log_audit(merchant_id: str, website_id: str, req: VerificationRequest, rep: TrustReport):
        with get_db() as conn:
            import json
            tx_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
            aud_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
            now_iso = time.strftime("%I:%M:%S %p")
            conn.execute("""
            INSERT INTO audit_logs (id, transaction_id, merchant_id, website_id, brand_name, target_url, product_name, amount, currency, trust_score, verdict, merchant_state, latency_ms, evidence_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                aud_id,
                tx_id,
                merchant_id,
                website_id,
                req.brand_name,
                req.merchant_url,
                req.product_name,
                req.price,
                req.currency,
                rep.trust_score,
                rep.action_taken,
                rep.merchant_status,
                rep.total_latency_ms,
                json.dumps(rep.evidence),
                now_iso
            ))
