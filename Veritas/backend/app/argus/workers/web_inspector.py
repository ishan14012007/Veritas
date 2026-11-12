import re
import time
from typing import Dict, Any
from app.argus.models import WorkerResult
from app.argus.workers.domain_forensics import extract_root_domain_and_tld

DEMO_DOMAINS_DATA = {
    "boat-lifestyle.com": {
        "title": "boAt Lifestyle - Official Website for Earphones, Headphones & Watches",
        "has_policies": True,
        "catalog_depth": 54,
        "dns_hash": "a1b2c3d4e5f6001",
        "cert_fingerprint": "SHA256:BOAT:CERT:2026"
    },
    "nike.com": {
        "title": "Nike. Just Do It. Nike IN - Official Shoes & Sportswear",
        "has_policies": True,
        "catalog_depth": 86,
        "dns_hash": "a1b2c3d4e5f6002",
        "cert_fingerprint": "SHA256:NIKE:CERT:2026"
    },
    "apple.com": {
        "title": "Apple (India) - Official Online Store",
        "has_policies": True,
        "catalog_depth": 42,
        "dns_hash": "a1b2c3d4e5f6003",
        "cert_fingerprint": "SHA256:APPL:CERT:2026"
    },
    "amazon.in": {
        "title": "Amazon.in - Online Shopping Site in India",
        "has_policies": True,
        "catalog_depth": 120,
        "dns_hash": "a1b2c3d4e5f6004",
        "cert_fingerprint": "SHA256:AMZN:CERT:2026"
    },
    "makemytrip.com": {
        "title": "MakeMyTrip - #1 Travel App, Flight, Hotel & Bus Booking",
        "has_policies": True,
        "catalog_depth": 75,
        "dns_hash": "a1b2c3d4e5f6005",
        "cert_fingerprint": "SHA256:MMTR:CERT:2026"
    }
}

def run_web_inspector(url: str) -> WorkerResult:
    start = time.perf_counter()
    root_domain, _ = extract_root_domain_and_tld(url)
    
    title = "Unknown Merchant"
    has_policy_links = False
    catalog_depth = 1
    dns_hash = "GEN-DNS-991"
    cert_fp = "GEN-CERT-991"
    
    # 1. Check known domain profiles
    if root_domain in DEMO_DOMAINS_DATA:
        cached = DEMO_DOMAINS_DATA[root_domain]
        title = cached["title"]
        has_policy_links = cached["has_policies"]
        catalog_depth = cached["catalog_depth"]
        dns_hash = cached["dns_hash"]
        cert_fp = cached["cert_fingerprint"]
    elif any(bad in url.lower() for bad in ["deals", "scam", "mega", "fest", "clearance", ".xyz", ".shop", ".top"]):
        title = "Exclusive Super Deal! Limited Stock - Buy Now"
        has_policy_links = False
        catalog_depth = 1  # 1-page landing phishing site
        dns_hash = "FAST-FLUX-PHISH-001"
        cert_fp = "UNTRUSTED-CERT"
    else:
        # Generic store / unknown merchant
        title = "Independent Verified Merchant"
        has_policy_links = True
        catalog_depth = 18
        dns_hash = "DNS-HASH-LEGIT"
        cert_fp = "VALID-TLS-2026"

    score = 90
    status = "PASS"
    if not has_policy_links:
        score -= 35
        status = "WARN"
    if catalog_depth <= 2:
        score -= 40
        status = "FAIL"

    latency = round((time.perf_counter() - start) * 1000, 2)
    return WorkerResult(
        name="Catalog & Policy Inspector",
        status=status,
        score=max(10, min(score, 100)),
        latency_ms=latency,
        details={
            "page_title": title,
            "has_mandatory_policies": has_policy_links,
            "catalog_depth_items": catalog_depth,
            "dns_hash": dns_hash,
            "cert_fingerprint": cert_fp,
            "single_page_scam_risk": catalog_depth <= 2 and not has_policy_links
        }
    )
