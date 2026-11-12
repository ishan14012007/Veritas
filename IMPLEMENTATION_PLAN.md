# IMPLEMENTATION PLAN: ARGUS & SHARED SERVER INFRASTRUCTURE

> **Document Status**: Draft / Awaiting User Approval  
> **Rule Reminder**: **NO CODE WILL BE IMPLEMENTED UNTIL EXPLICIT USER APPROVAL IS GIVEN.**  
> **Scope**: Implementation strictly of **ARGUS** and the shared **SERVER** infrastructure.

---

## 1. Project Directory Layout

We will organize the repository to cleanly decouple Argus, Accord, and Server, matching the architectural decisions made during brainstorming:

```text
x:\hackathon\
├── server\
│   ├── __init__.py
│   ├── database.py             # Database engine & session management (SQLite / WAL)
│   ├── models.py               # SQLAlchemy ORM models (Merchants, Websites, Associations, Appeals)
│   ├── registry.py             # Global Merchant Trust Registry manager
│   ├── cache_manager.py        # 7-day conditional cache & invalidation engine
│   └── single_flight.py        # Concurrency deduplication (prevents duplicate crawling)
│
├── argus\
│   ├── __init__.py
│   ├── engine.py               # Parallel verification orchestrator
│   ├── workers\
│   │   ├── domain_forensics.py # Worker 1: Typosquatting, TLD risk, homoglyphs
│   │   ├── web_inspector.py    # Worker 2: DOM policies, catalog depth, contact info
│   │   ├── price_anomaly.py    # Worker 3: MSRP ratio & market anomaly reasoning
│   │   └── synthesizer.py      # Worker 4: Composite score & 3-tier risk decision
│   ├── appeals.py              # Merchant grievance & appeal ticket workflow
│   └── paypal_gateway.py       # PayPal Sandbox Orders API (Authorize, Capture, Void)
│
├── static\
│   ├── index.html              # Argus Security Operations Dashboard
│   ├── css\styles.css          # Dark-mode fintech styling
│   └── js\
│       ├── app.js              # Live state management & checkout simulation
│       └── ag_grid_setup.js    # AG Grid configuration for registry, audit, and appeals
│
├── tests\
│   ├── test_registry.py        # Verifies 7-day caching and change-detection invalidation
│   ├── test_single_flight.py   # Verifies concurrent request deduplication
│   └── test_mitigation.py      # Verifies 3-tier risk logic & PayPal void calls
│
├── docs\
│   ├── PROJECT_OVERVIEW.md
│   ├── SYSTEM_ARCHITECTURE.md
│   └── IMPLEMENTATION_PLAN.md
│
├── app.py                      # Main entry point (FastAPI server exposing REST APIs)
├── requirements.txt            # Python dependencies
└── README.md                   # Devpost submission documentation
```

---

## 2. Phase-by-Phase Roadmap

### Phase 1: Database & Server Registry Foundation
* **Goal**: Establish the persistent relational data model for merchants, websites, associations, audit logs, and appeal tickets.
* **Tasks**:
  1. Implement `server/database.py` with SQLite (WAL mode enabled for fast concurrent read/writes).
  2. Define schemas in `server/models.py` (`Merchant`, `Website`, `MerchantWebsite`, `AuditLog`, `AppealTicket`).
  3. Implement `server/registry.py` with CRUD methods for merchant identity lookup, website domain lookup, and association records.

### Phase 2: 7-Day Caching & Single-Flight Concurrency
* **Goal**: Optimize system performance and prevent server overload from thundering-herd checkout requests.
* **Tasks**:
  1. Implement `server/cache_manager.py`:
     - Calculate 7-day TTL: `expires_at = verified_at + timedelta(days=7)`.
     - Invalidation hook: Detect DNS hash / TLS thumbprint changes to force re-verification before the 7 days expire.
  2. Implement `server/single_flight.py`:
     - In-memory async lock table keyed on root domain (`root_domain`).
     - If a verification job is active, queue subsequent callers onto the active future; fan out the final `TrustReport` once completed.

### Phase 3: Argus Parallel Forensic Engine & 3-Tier Mitigation
* **Goal**: Implement multi-threaded / asynchronous forensic workers that evaluate transactions in parallel.
* **Tasks**:
  1. Refine `domain_forensics.py`: Official brand dictionary, high-risk TLD checks, Levenshtein distance typosquatting.
  2. Refine `web_inspector.py`: DOM parsing for mandatory policies (Privacy, Terms, Refund, Contact) and catalog depth scoring.
  3. Refine `price_anomaly.py`: Benchmark MSRP floor pricing logic.
  4. Implement `synthesizer.py` with **3-Tier Risk Hierarchy**:
     - **Low Risk (Score ≥ 70)**: `APPROVED_FOR_CAPTURE`.
     - **Medium Risk (Score 45–69)**: `WARNED_REQUIRE_CONFIRMATION`.
     - **High-Confidence Fraud (Score < 45)**: `VOIDED_AND_QUARANTINED`.

### Phase 4: Merchant Grievance & Appeal Resolution Workflow
* **Goal**: Eliminate the "dead-end" problem for merchants flagged by automated heuristics.
* **Tasks**:
  1. Implement `argus/appeals.py`:
     - `create_appeal_ticket(merchant_id, incident_id, statement, docs)`
     - `resolve_appeal_ticket(ticket_id, action, admin_notes)`
  2. When an appeal is resolved as `APPROVED`:
     - Update merchant record to `VERIFIED`.
     - Update association record to `AUTHORIZED`.
     - Reset 7-day cache timestamp.

### Phase 5: AG Grid Security Operations Center (Frontend)
* **Goal**: Provide an enterprise data-management UI fulfilling the AG Grid Sponsor Track.
* **Tasks**:
  1. **Tab 1: Live Transaction Interceptor & Simulator**:
     - Fast demo presets (Nike, boAt, Amazon phishing, Apple scam).
     - Live parallel worker progress matrix with millisecond latency gauges.
     - Yellow PayPal smart button.
  2. **Tab 2: Global Merchant Trust Registry (AG Grid)**:
     - Searchable, sortable grid of all discovered merchants, domains, and trust scores.
  3. **Tab 3: Incident Audit Log & Evidence Dossier (AG Grid)**:
     - Itemized list of all intercepted threats with drill-down forensic logs.
  4. **Tab 4: Merchant Appeal Center**:
     - View open tickets, inspect submitted evidence, and click "Approve Appeal" to restore quarantined merchants live in front of judges!

### Phase 6: End-to-End Verification, Video Script & Documentation
* **Goal**: Validate end-to-end user flows and prepare Devpost submission assets.
* **Tasks**:
  1. Run automated test suite (`tests/`).
  2. Document API contracts for Accord teammate.
  3. Prepare 2-minute demo video script showcasing the 4 core pillars:
     - Instant parallel check.
     - Phishing detection & instant quarantine.
     - 7-day cache reuse (< 2 ms).
     - Merchant appeal resolution live demo.

---

## 3. Verification & Validation Checklist

Before marking the implementation ready, we must verify:
- [ ] **Decoupling**: Can Argus start and run complete verifications with Accord offline?
- [ ] **Performance**: Does a cached merchant return a response in `< 5 ms`?
- [ ] **Deduplication**: Do 10 concurrent requests to an unverified domain trigger only 1 crawler job?
- [ ] **Enforcement**: Does a phishing attempt properly trigger `VOID` and flag the merchant as `FROZEN_AND_QUARANTINED`?
- [ ] **Appeal Cycle**: Does resolving an appeal ticket in the dashboard restore the merchant to `AUTHORIZED`?
- [ ] **AG Grid Feature Set**: Are filtering, column resizing, sorting, and custom status renderers working smoothly?

---

> **AWAITING USER FEEDBACK**:
> Please review the architecture, requirements, and implementation plan. 
> Once you confirm and approve, we will begin Phase 1!
