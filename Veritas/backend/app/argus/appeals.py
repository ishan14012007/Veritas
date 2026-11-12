import uuid
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.argus.database import get_db
from app.argus.models import AppealCreate, AppealResolution
from server.registry import MerchantRegistry
from server.cache_manager import CacheManager

class AppealsManager:
    @staticmethod
    def create_appeal(req: AppealCreate) -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()
            app_id = f"APP-{uuid.uuid4().hex[:6].upper()}"
            now_iso = datetime.now(timezone.utc).isoformat()
            docs_json = json.dumps(req.submitted_documents or [])
            
            # Ensure merchant exists in registry so foreign key is satisfied
            cursor.execute("SELECT id FROM merchants WHERE id = ?;", (req.merchant_id,))
            merchant_row = cursor.fetchone()
            if not merchant_row:
                legal_name = f"Merchant Store ({req.merchant_id})"
                cursor.execute("""
                INSERT INTO merchants (id, paypal_merchant_id, legal_business_name, identity_status, overall_reputation_score, created_at)
                VALUES (?, ?, ?, 'UNDER_APPEAL', 25, ?);
                """, (req.merchant_id, f"PPM-{req.merchant_id}", legal_name, now_iso))
            else:
                cursor.execute("UPDATE merchants SET identity_status = 'UNDER_APPEAL' WHERE id = ?;", (req.merchant_id,))
            
            cursor.execute("""
            INSERT INTO appeals (id, merchant_id, incident_reference_id, status, reason_category, statement, submitted_documents, created_at, updated_at)
            VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?, ?);
            """, (app_id, req.merchant_id, req.incident_reference_id, req.reason_category, req.statement, docs_json, now_iso, now_iso))
            
            cursor.execute("SELECT * FROM appeals WHERE id = ?;", (app_id,))
            return dict(cursor.fetchone())

    @staticmethod
    def resolve_appeal(req: AppealResolution) -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appeals WHERE id = ?;", (req.ticket_id,))
            appeal = cursor.fetchone()
            if not appeal:
                raise ValueError("Appeal ticket not found")
                
            now_iso = datetime.now(timezone.utc).isoformat()
            new_status = "RESOLVED" if req.action == "APPROVE" else "REJECTED"
            
            cursor.execute("""
            UPDATE appeals
            SET status = ?, resolution_notes = ?, updated_at = ?
            WHERE id = ?;
            """, (new_status, req.resolution_notes, now_iso, req.ticket_id))
            
            merchant_id = appeal["merchant_id"]
            
            if req.action == "APPROVE":
                # Restore merchant identity in the same atomic transaction
                cursor.execute("""
                UPDATE merchants SET identity_status = 'VERIFIED', overall_reputation_score = 85 WHERE id = ?;
                """, (merchant_id,))
                
                # Restore merchant associations to AUTHORIZED and grant fresh 7-day cache
                verified_at, expires_at = CacheManager.compute_expiry(days=7)
                cursor.execute("""
                UPDATE merchant_websites
                SET association_status = 'AUTHORIZED', trust_score = 85, verified_at = ?, expires_at = ?
                WHERE merchant_id = ?;
                """, (verified_at, expires_at, merchant_id))
                print(f"[APPEALS] Merchant {merchant_id} successfully restored to VERIFIED via approved appeal {req.ticket_id}.")
            else:
                cursor.execute("""
                UPDATE merchants SET identity_status = 'RESTRICTED', overall_reputation_score = 20 WHERE id = ?;
                """, (merchant_id,))
                cursor.execute("""
                UPDATE merchant_websites
                SET association_status = 'REVOKED'
                WHERE merchant_id = ?;
                """, (merchant_id,))

            cursor.execute("SELECT * FROM appeals WHERE id = ?;", (req.ticket_id,))
            return dict(cursor.fetchone())

    @staticmethod
    def list_appeals() -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT 
                a.id,
                a.merchant_id,
                COALESCE(m.legal_business_name, a.merchant_id) as merchant_name,
                COALESCE(m.paypal_merchant_id, a.merchant_id) as paypal_merchant_id,
                a.incident_reference_id,
                a.status,
                a.reason_category,
                a.statement,
                a.submitted_documents,
                a.resolution_notes,
                a.created_at,
                a.updated_at
            FROM appeals a
            LEFT JOIN merchants m ON a.merchant_id = m.id
            ORDER BY a.created_at DESC;
            """)
            return [dict(r) for r in cursor.fetchall()]
