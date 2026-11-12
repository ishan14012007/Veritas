import time
from typing import Dict, Any
from server.models import WorkerResult

BENCHMARK_FLOOR_PRICES = {
    "iphone": 750.0,
    "macbook": 950.0,
    "airpods": 120.0,
    "playstation": 400.0,
    "camera": 350.0,
    "shoes": 45.0,
    "headphones": 25.0,
    "smartwatch": 40.0,
    "hotel": 30.0
}

def run_price_anomaly(product: str, price: float, brand: str) -> WorkerResult:
    start = time.perf_counter()
    status = "PASS"
    score = 90
    anomaly_detected = False
    ratio = 1.0
    
    prod_lower = product.lower()
    expected_floor = None
    
    for k, v in BENCHMARK_FLOOR_PRICES.items():
        if k in prod_lower:
            expected_floor = v
            break
            
    if expected_floor:
        if price < (expected_floor * 0.20): # Price < 20% of MSRP (e.g. $15 iPhone)
            anomaly_detected = True
            score = 15
            status = "FAIL"
            ratio = price / expected_floor
        elif price < (expected_floor * 0.50): # Price < 50% of MSRP
            score = 55
            status = "WARN"
            ratio = price / expected_floor

    latency = round((time.perf_counter() - start) * 1000, 2)
    return WorkerResult(
        name="Price Anomaly AI",
        status=status,
        score=score,
        latency_ms=latency,
        details={
            "product_analyzed": product,
            "price_received": price,
            "expected_floor_price": expected_floor,
            "anomaly_detected": anomaly_detected,
            "discount_ratio": round(ratio, 2)
        }
    )
