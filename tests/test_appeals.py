import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from server.models import AppealCreate, AppealResolution
from server.registry import MerchantRegistry
from argus.appeals import AppealsManager

def test_merchant_appeal_lifecycle():
    # 1. Setup a restricted merchant
    m = MerchantRegistry.get_or_create_merchant("P-MCH-DISPUTE-01", "Falsely Flagged Electronics")
    MerchantRegistry.update_merchant_status(m["id"], "FROZEN_AND_QUARANTINED", 25)
    
    # 2. Merchant raises an appeal ticket
    appeal_req = AppealCreate(
        merchant_id=m["id"],
        incident_reference_id="INC-SEAL-TEST01",
        reason_category="BRAND_MISMATCH",
        statement="We are an authorized distributor with signed distributor contract.",
        submitted_documents=["https://proof.example.com/contract.pdf"]
    )
    ticket = AppealsManager.create_appeal(appeal_req)
    assert ticket["status"] == "OPEN"
    print(f"[PASS] Appeal raised: Ticket {ticket['id']} in status 'OPEN'")

    # 3. Admin / Auditor approves appeal
    resolution_req = AppealResolution(
        ticket_id=ticket["id"],
        action="APPROVE",
        resolution_notes="Authorized distributor credentials verified."
    )
    resolved = AppealsManager.resolve_appeal(resolution_req)
    assert resolved["status"] == "RESOLVED"
    
    # 4. Verify merchant identity status restored
    m_restored = MerchantRegistry.get_or_create_merchant("P-MCH-DISPUTE-01", "Falsely Flagged Electronics")
    assert m_restored["identity_status"] == "VERIFIED"
    assert m_restored["overall_reputation_score"] == 85
    print(f"[PASS] Appeal approved: Merchant {m['id']} restored to VERIFIED (Reputation: 85)")

if __name__ == "__main__":
    test_merchant_appeal_lifecycle()
    print("ALL APPEALS TESTS PASSED!")
