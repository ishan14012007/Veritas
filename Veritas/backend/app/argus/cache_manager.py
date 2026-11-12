import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from app.argus.database import get_db

CACHE_TTL_DAYS = 7

class CacheManager:
    @staticmethod
    def evaluate_cache(association: Optional[Dict[str, Any]], current_dns_hash: Optional[str] = None) -> Tuple[bool, Optional[float], Optional[Dict[str, Any]]]:
        """
        Evaluates whether a cached verification record can be safely reused.
        Returns: (is_valid_cache_hit, cache_age_days, cached_data)
        """
        if not association:
            return False, None, None
            
        status = association.get("association_status")
        if status != "AUTHORIZED":
            # Negative states (QUARANTINED, REVOKED, UNVERIFIED) are not cached approvals
            return False, None, None
            
        expires_at_str = association.get("expires_at")
        verified_at_str = association.get("verified_at")
        
        if not expires_at_str or not verified_at_str:
            return False, None, None
            
        try:
            now_dt = datetime.now(timezone.utc)
            expires_at = datetime.fromisoformat(expires_at_str)
            verified_at = datetime.fromisoformat(verified_at_str)
            
            # 1. Temporal Expiry Check
            if now_dt >= expires_at:
                return False, None, None # Expired, must reverify
                
            # 2. Conditional Change Detection
            # If current request provides a DNS hash that differs from stored baseline, invalidate immediately!
            stored_dns = association.get("dns_hash")
            if current_dns_hash and stored_dns and current_dns_hash != stored_dns:
                CacheManager.invalidate(association["merchant_id"], association["website_id"], "DNS_RECORDS_ALTERED")
                return False, None, None
                
            age_days = round((now_dt - verified_at).total_seconds() / 86400, 2)
            
            evidence_json = association.get("evidence_dossier")
            evidence = json.loads(evidence_json) if evidence_json else []
            
            cached_data = {
                "trust_score": association["trust_score"],
                "association_status": association["association_status"],
                "evidence": evidence,
                "verified_at": verified_at_str,
                "expires_at": expires_at_str
            }
            return True, age_days, cached_data
            
        except Exception:
            return False, None, None

    @staticmethod
    def compute_expiry(days: int = CACHE_TTL_DAYS) -> Tuple[str, str]:
        now_dt = datetime.now(timezone.utc)
        expires_dt = now_dt + timedelta(days=days)
        return now_dt.isoformat(), expires_dt.isoformat()

    @staticmethod
    def invalidate(merchant_id: str, website_id: str, reason: str = "MANUAL_OR_DETECTED_CHANGE"):
        """Invalidates the 7-day cache for a merchant-website pair."""
        with get_db() as conn:
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute("""
            UPDATE merchant_websites
            SET expires_at = ?
            WHERE merchant_id = ? AND website_id = ?;
            """, (now_iso, merchant_id, website_id))
            print(f"[CACHE] Invalidated cache for merchant {merchant_id} on site {website_id}. Reason: {reason}")
