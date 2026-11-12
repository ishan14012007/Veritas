import uuid
import time
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from server.database import get_db
from server.models import MerchantRecord, WebsiteRecord, AssociationRecord

def current_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class MerchantRegistry:
    @staticmethod
    def get_or_create_merchant(paypal_merchant_id: str, legal_business_name: str) -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM merchants WHERE paypal_merchant_id = ?;", (paypal_merchant_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            m_id = f"MCH-{uuid.uuid4().hex[:8].upper()}"
            now = current_iso()
            cursor.execute("""
            INSERT INTO merchants (id, paypal_merchant_id, legal_business_name, identity_status, overall_reputation_score, created_at)
            VALUES (?, ?, ?, 'PENDING', 50, ?);
            """, (m_id, paypal_merchant_id, legal_business_name, now))
            
            cursor.execute("SELECT * FROM merchants WHERE id = ?;", (m_id,))
            return dict(cursor.fetchone())

    @staticmethod
    def get_or_create_website(root_domain: str, tld: str) -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM websites WHERE root_domain = ?;", (root_domain.lower(),))
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            w_id = f"WEB-{uuid.uuid4().hex[:8].upper()}"
            cursor.execute("""
            INSERT INTO websites (id, root_domain, tld, status)
            VALUES (?, ?, ?, 'ACTIVE');
            """, (w_id, root_domain.lower(), tld.lower()))
            
            cursor.execute("SELECT * FROM websites WHERE id = ?;", (w_id,))
            return dict(cursor.fetchone())

    @staticmethod
    def get_association(merchant_id: str, website_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT mw.*, m.paypal_merchant_id, m.legal_business_name, m.identity_status, w.root_domain, w.dns_hash
            FROM merchant_websites mw
            JOIN merchants m ON mw.merchant_id = m.id
            JOIN websites w ON mw.website_id = w.id
            WHERE mw.merchant_id = ? AND mw.website_id = ?;
            """, (merchant_id, website_id))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def upsert_association(
        merchant_id: str,
        website_id: str,
        brand_name_claimed: str,
        association_status: str,
        trust_score: int,
        verified_at: Optional[str],
        expires_at: Optional[str],
        evidence_dossier: List[str]
    ) -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM merchant_websites WHERE merchant_id = ? AND website_id = ?;", (merchant_id, website_id))
            row = cursor.fetchone()
            
            evidence_json = json.dumps(evidence_dossier)
            if row:
                mw_id = row["id"]
                cursor.execute("""
                UPDATE merchant_websites
                SET brand_name_claimed = ?, association_status = ?, trust_score = ?, verified_at = ?, expires_at = ?, evidence_dossier = ?
                WHERE id = ?;
                """, (brand_name_claimed, association_status, trust_score, verified_at, expires_at, evidence_json, mw_id))
            else:
                mw_id = f"MW-{uuid.uuid4().hex[:8].upper()}"
                cursor.execute("""
                INSERT INTO merchant_websites (id, merchant_id, website_id, brand_name_claimed, association_status, trust_score, verified_at, expires_at, evidence_dossier)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (mw_id, merchant_id, website_id, brand_name_claimed, association_status, trust_score, verified_at, expires_at, evidence_json))
            
            cursor.execute("SELECT * FROM merchant_websites WHERE id = ?;", (mw_id,))
            return dict(cursor.fetchone())

    @staticmethod
    def update_merchant_status(merchant_id: str, status: str, reputation_score: Optional[int] = None):
        with get_db() as conn:
            cursor = conn.cursor()
            if reputation_score is not None:
                cursor.execute("""
                UPDATE merchants SET identity_status = ?, overall_reputation_score = ? WHERE id = ?;
                """, (status, reputation_score, merchant_id))
            else:
                cursor.execute("""
                UPDATE merchants SET identity_status = ? WHERE id = ?;
                """, (status, merchant_id))

    @staticmethod
    def list_all_records() -> List[Dict[str, Any]]:
        """Returns joined registry rows for AG Grid."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT 
                mw.id as association_id,
                m.id as merchant_id,
                m.paypal_merchant_id,
                m.legal_business_name,
                m.identity_status,
                w.root_domain,
                w.tld,
                w.status as website_status,
                mw.brand_name_claimed,
                mw.association_status,
                mw.trust_score,
                mw.verified_at,
                mw.expires_at
            FROM merchant_websites mw
            JOIN merchants m ON mw.merchant_id = m.id
            JOIN websites w ON mw.website_id = w.id
            ORDER BY mw.verified_at DESC;
            """)
            return [dict(r) for r in cursor.fetchall()]

def seed_default_registry():
    """Seeds baseline verified merchants and known legitimate domain associations."""
    defaults = [
        {"paypal_id": "P-MCH-NIKE01", "name": "Nike Global Inc.", "brand": "Nike", "domain": "nike.com", "tld": ".com", "score": 98},
        {"paypal_id": "P-MCH-BOAT01", "name": "Imagine Marketing Ltd. (boAt)", "brand": "boAt Lifestyle", "domain": "boat-lifestyle.com", "tld": ".com", "score": 95},
        {"paypal_id": "P-MCH-APPL01", "name": "Apple Distribution International", "brand": "Apple", "domain": "apple.com", "tld": ".com", "score": 99},
        {"paypal_id": "P-MCH-AMZN01", "name": "Amazon Seller Services Pvt Ltd", "brand": "Amazon India", "domain": "amazon.in", "tld": ".in", "score": 98},
        {"paypal_id": "P-MCH-MMTR01", "name": "MakeMyTrip India Pvt Ltd", "brand": "MakeMyTrip", "domain": "makemytrip.com", "tld": ".com", "score": 96}
    ]
    
    from datetime import timedelta
    now_dt = datetime.now(timezone.utc)
    verified_at = now_dt.isoformat()
    expires_at = (now_dt + timedelta(days=7)).isoformat()
    
    for item in defaults:
        m = MerchantRegistry.get_or_create_merchant(item["paypal_id"], item["name"])
        MerchantRegistry.update_merchant_status(m["id"], "VERIFIED", item["score"])
        
        w = MerchantRegistry.get_or_create_website(item["domain"], item["tld"])
        
        # update website policies
        with get_db() as conn:
            conn.execute("UPDATE websites SET has_mandatory_policies = 1, catalog_depth = 50, status = 'ACTIVE' WHERE id = ?;", (w["id"],))
            
        MerchantRegistry.upsert_association(
            merchant_id=m["id"],
            website_id=w["id"],
            brand_name_claimed=item["brand"],
            association_status="AUTHORIZED",
            trust_score=item["score"],
            verified_at=verified_at,
            expires_at=expires_at,
            evidence_dossier=[
                f"Domain verified: '{item['domain']}' is officially registered to {item['brand']}.",
                "Mandatory consumer policies (Refund, Privacy, Terms) verified active.",
                "Merchant identity established through PayPal Enterprise partnership."
            ]
        )

if __name__ == "__main__":
    seed_default_registry()
    print("Default merchant registry seeded successfully.")
    records = MerchantRegistry.list_all_records()
    print(f"Total seeded records: {len(records)}")
