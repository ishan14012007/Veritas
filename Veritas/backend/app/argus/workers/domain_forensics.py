import re
import time
from urllib.parse import urlparse
from typing import Dict, Any, Tuple
from app.argus.models import WorkerResult

OFFICIAL_BRAND_DOMAINS = {
    "amazon": ["amazon.com", "amazon.in", "amazon.co.uk", "amazon.de", "amazon.ca", "amazon.co.jp"],
    "apple": ["apple.com", "imagineonline.store", "aptronixindia.com"],
    "nike": ["nike.com"],
    "boat": ["boat-lifestyle.com"],
    "sony": ["sony.com", "sony.co.in", "shopatsc.com"],
    "samsung": ["samsung.com"],
    "makemytrip": ["makemytrip.com"],
    "paypal": ["paypal.com"],
    "adidas": ["adidas.com", "adidas.co.in"]
}

HIGH_RISK_TLDS = {".xyz", ".top", ".click", ".shop", ".buzz", ".club", ".icu", ".cam", ".site", ".tk", ".cf", ".ga"}

def clean_brand_key(brand: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', brand.lower())
    for known in OFFICIAL_BRAND_DOMAINS:
        if known in cleaned:
            return known
    return cleaned

def extract_root_domain_and_tld(url: str) -> Tuple[str, str]:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    hostname = (parsed.hostname or url).lower()
    parts = hostname.split('.')
    if len(parts) >= 2:
        root_domain = ".".join(parts[-2:])
        tld = "." + parts[-1]
        return root_domain, tld
    return hostname, ".com"

def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def run_domain_forensics(brand: str, url: str) -> WorkerResult:
    start = time.perf_counter()
    root_domain, tld = extract_root_domain_and_tld(url)
    brand_key = clean_brand_key(brand)
    
    status = "PASS"
    score = 95
    details = {
        "root_domain": root_domain,
        "tld": tld,
        "is_suspicious_tld": False,
        "is_typosquatting": False,
        "official_domain_match": False,
        "levenshtein_distance": None
    }
    
    # 1. Check TLD
    if tld in HIGH_RISK_TLDS or any(root_domain.endswith(bad) for bad in HIGH_RISK_TLDS):
        details["is_suspicious_tld"] = True
        score -= 35
        status = "WARN"
        
    # 2. Check Official Brand Alignment
    if brand_key in OFFICIAL_BRAND_DOMAINS:
        official_list = OFFICIAL_BRAND_DOMAINS[brand_key]
        if any(root_domain == off or root_domain.endswith("." + off) for off in official_list):
            details["official_domain_match"] = True
            score = 100
            status = "PASS"
        else:
            # Check for typosquatting / homoglyphs (e.g. amaz0n vs amazon)
            domain_name = root_domain.split('.')[0]
            # Replace common substitutions (0 -> o, 1 -> l)
            normalized = domain_name.replace('0', 'o').replace('1', 'l')
            dist = levenshtein_distance(normalized, brand_key)
            details["levenshtein_distance"] = dist
            
            is_squatted = (dist <= 2 and dist > 0) or (brand_key in domain_name)
            details["is_typosquatting"] = is_squatted
            
            score -= 60
            status = "FAIL"
    else:
        # Unknown/emerging brand
        if details["is_suspicious_tld"]:
            status = "WARN"
            score = 55
        else:
            status = "PASS"
            score = 80
            
    latency = round((time.perf_counter() - start) * 1000, 2)
    return WorkerResult(
        name="Domain Forensics",
        status=status,
        score=max(5, min(score, 100)),
        latency_ms=latency,
        details=details
    )
