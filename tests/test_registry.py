import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from server.database import init_db
from server.registry import MerchantRegistry
from server.cache_manager import CacheManager

def test_registry_and_7day_cache():
    init_db()
    
    # 1. Create merchant and website
    m = MerchantRegistry.get_or_create_merchant("TEST-P-MCH-001", "Test Merchant Ltd")
    w = MerchantRegistry.get_or_create_website("teststore.com", ".com")
    
    assert m["paypal_merchant_id"] == "TEST-P-MCH-001"
    assert w["root_domain"] == "teststore.com"
    
    # 2. Upsert authorized association with 7-day expiry
    v_at, exp_at = CacheManager.compute_expiry(days=7)
    assoc = MerchantRegistry.upsert_association(
        merchant_id=m["id"],
        website_id=w["id"],
        brand_name_claimed="TestBrand",
        association_status="AUTHORIZED",
        trust_score=95,
        verified_at=v_at,
        expires_at=exp_at,
        evidence_dossier=["Domain verified test"]
    )
    
    # 3. Evaluate Cache (Should HIT)
    loaded_assoc = MerchantRegistry.get_association(m["id"], w["id"])
    is_hit, age, cached_data = CacheManager.evaluate_cache(loaded_assoc)
    assert is_hit is True
    assert cached_data["trust_score"] == 95
    print("[PASS] Cache evaluation: 7-day cache HIT successfully validated.")
    
    # 4. Invalidate Cache
    CacheManager.invalidate(m["id"], w["id"], "TEST_INVALIDATION")
    loaded_assoc2 = MerchantRegistry.get_association(m["id"], w["id"])
    is_hit2, _, _ = CacheManager.evaluate_cache(loaded_assoc2)
    assert is_hit2 is False
    print("[PASS] Cache invalidation: Expired cache correctly forces re-verification.")

if __name__ == "__main__":
    test_registry_and_7day_cache()
    print("ALL REGISTRY TESTS PASSED!")
