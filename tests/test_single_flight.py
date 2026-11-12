import os
import sys
import time
import concurrent.futures

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from server.single_flight import SingleFlightGroup

def test_single_flight_deduplication():
    group = SingleFlightGroup()
    execution_counter = 0

    def expensive_crawl_simulation(domain: str):
        nonlocal execution_counter
        execution_counter += 1
        time.sleep(0.1) # Simulate network crawl
        return f"Verified-{domain}"

    # Spawn 10 concurrent threads for the exact same domain
    threads = 10
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(group.execute, "heavy-traffic-store.com", expensive_crawl_simulation, "heavy-traffic-store.com") for _ in range(threads)]
        results = [f.result() for f in futures]

    # Verify all 10 callers got the correct result
    for res, subscribers in results:
        assert res == "Verified-heavy-traffic-store.com"
        
    # Crucial assertion: Function must have executed exactly ONCE!
    assert execution_counter == 1
    print(f"[PASS] Single-Flight: {threads} concurrent requests executed expensive crawl exactly {execution_counter} time.")

if __name__ == "__main__":
    test_single_flight_deduplication()
    print("ALL SINGLE-FLIGHT TESTS PASSED!")
