import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from server.models import VerificationRequest
from app import verify_checkout_intent, get_merchant_registry, get_audit_log, get_appeals, create_paypal_order, OrderCreateReq

def test_api_functions():
    # 1. Registry API
    reg_data = get_merchant_registry()
    assert len(reg_data) >= 5
    print(f"[PASS] get_merchant_registry(): {len(reg_data)} records returned.")

    # 2. Checkout Verify API (Nike - 7-Day Cache Hit)
    rep_v1 = verify_checkout_intent(VerificationRequest(
        brand_name="Nike",
        merchant_url="https://www.nike.com/in/t/air-jordan-1-retro",
        product_name="Air Jordan 1",
        price=180.0
    ))
    assert rep_v1.trust_score >= 70
    assert rep_v1.action_taken == "APPROVED_FOR_CAPTURE"
    print(f"[PASS] verify_checkout_intent(Nike): Score={rep_v1.trust_score}, Action={rep_v1.action_taken}, CacheHit={rep_v1.cache_hit}, Latency={rep_v1.total_latency_ms}ms")

    # 3. Checkout Verify API (Amazon Phish - Blocked & Account Sealed)
    rep_v2 = verify_checkout_intent(VerificationRequest(
        brand_name="Amazon India",
        merchant_url="https://amaz0n-mega-deals.xyz/buy/airpods",
        product_name="Apple AirPods Pro 2",
        price=14.99
    ))
    assert rep_v2.trust_score < 45
    assert rep_v2.action_taken == "TRANSACTION_VOIDED_AND_ACCOUNT_SEALED"
    print(f"[PASS] verify_checkout_intent(Phish): Score={rep_v2.trust_score}, Action={rep_v2.action_taken}, Merchant={rep_v2.merchant_status}")

    # 4. Audit Log API
    aud_data = get_audit_log(limit=10)
    assert len(aud_data) >= 2
    print(f"[PASS] get_audit_log(): {len(aud_data)} audit entries returned.")

    # 5. Appeals API
    app_data = get_appeals()
    print(f"[PASS] get_appeals(): {len(app_data)} tickets returned.")

    # 6. PayPal Orders Sandbox API
    order_data = create_paypal_order(OrderCreateReq(amount=180.0, brand_name="Nike"))
    assert order_data["status"] == "CREATED"
    assert order_data["intent"] == "AUTHORIZE"
    print(f"[PASS] create_paypal_order(): Order ID {order_data['order_id']} created with intent '{order_data['intent']}'.")

if __name__ == "__main__":
    test_api_functions()
    print("ALL API ENDPOINT INTEGRATION TESTS PASSED!")
