import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from server.models import VerificationRequest
from argus.engine import ArgusEngine

def test_3tier_risk_mitigation():
    # 1. Test Legitimate Store (Nike) -> Low Risk (ALLOW)
    req_legit = VerificationRequest(
        brand_name="Nike",
        merchant_url="https://www.nike.com/in/t/air-jordan-1-retro",
        product_name="Air Jordan 1 Retro",
        price=180.00
    )
    rep_legit = ArgusEngine.verify_transaction(req_legit)
    assert rep_legit.trust_score >= 70
    assert rep_legit.action_taken == "APPROVED_FOR_CAPTURE"
    assert rep_legit.merchant_status == "ACTIVE"
    print(f"[PASS] Tier 1 (Low Risk): Nike scored {rep_legit.trust_score}/100 -> {rep_legit.action_taken}")

    # 2. Test Phishing Store (Amazon Impersonation on .xyz) -> High Risk (VOID & SEAL)
    req_phish = VerificationRequest(
        brand_name="Amazon India",
        merchant_url="https://amaz0n-mega-deals.xyz/buy/airpods",
        product_name="Apple AirPods Pro 2",
        price=14.99
    )
    rep_phish = ArgusEngine.verify_transaction(req_phish)
    assert rep_phish.trust_score < 45
    assert rep_phish.action_taken == "TRANSACTION_VOIDED_AND_ACCOUNT_SEALED"
    assert rep_phish.merchant_status == "FROZEN_AND_QUARANTINED"
    assert rep_phish.incident_reference_id is not None
    print(f"[PASS] Tier 3 (High-Confidence Fraud): Phish scored {rep_phish.trust_score}/100 -> {rep_phish.action_taken} (Incident: {rep_phish.incident_reference_id})")

if __name__ == "__main__":
    test_3tier_risk_mitigation()
    print("ALL MITIGATION TESTS PASSED!")
