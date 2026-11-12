# 🛡️ ARGUS: Autonomous Merchant Trust Registry & Pre-Settlement Fraud Interceptor
> **Built for the PayPal AI Hackathon 2026 (Devpost)**  
> **Categories Targeted**: Best Use of Agentic Commerce ($5,000) • Most Impactful ($5,000) • Best Use of PayPal Tools ($5,000) • AG Grid Sponsor Award • Postman Sponsor Award • Render Cloud Deployment

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-brightgreen.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![SQLite WAL](https://img.shields.io/badge/Storage-SQLite_WAL-003B57.svg)](https://sqlite.org)
[![AG Grid](https://img.shields.io/badge/Sponsor-AG_Grid-brightgreen)](https://www.ag-grid.com/)
[![Postman](https://img.shields.io/badge/Postman-API_Collection_v2.1-FF6C37.svg•logo=postman)](postman/argus_api_collection.json)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)
[![PayPal Sandbox](https://img.shields.io/badge/PayPal-Orders_API_v2-003087.svg)](https://developer.paypal.com)

---

## 📌 Executive Summary

Digital commerce has fundamentally reduced transaction friction, but it has drastically amplified the **cost of mistrust**. When malicious actors exploit checkout payment gateways, they declare trusted brand names (e.g., `"Amazon India"`, `"Apple Store"`, `"Nike"`) while pairing them with rogue, lookalike, or disposable domains (e.g., `amaz0n-mega-deals.xyz`). Unsuspecting buyers authorize transactions thinking they are paying the legitimate brand.

The resulting fallout is severe: buyers suffer financial loss, legitimate merchants suffer brand damage, and payment networks bear millions of dollars in customer disputes, chargebacks, and manual arbitration.

**Argus** is an autonomous, real-time merchant identity verification, domain forensics, and fraud mitigation platform. Designed specifically for PayPal's pre-settlement lifecycle, Argus inspects transaction intent in parallel to eliminate buyer checkout latency, deploys a 3-tier risk mitigation engine with automated quarantines, maintains a persistent Global Merchant Trust Registry with 7-day conditional verification caching, and provides an explainable Merchant Grievance & Appeal System to prevent permanent false-positive account lockouts.

---

## 🏗️ System Architecture

```
[ Customer Clicks 'Pay with PayPal' ]
               │
               ▼  (1) Instant Pre-Settlement Hold (intent: "AUTHORIZE")
      [ User Sees Order Processing (< 10 ms) ]
               │
               ├──────────────────────────┐
      [ 7-Day Cache HIT• ]                │ (Cache Miss or Change Detected)
      (Evaluates TTL & DNS Hash)          │
               │                          ▼
               │              [ Single-Flight Concurrency ]
               │              (Deduplicates concurrent crawls)
               │                          │
               │                          ├───────────────┬───────────────┐
               │                          │ Worker 1      │ Worker 2      │ Worker 3
               │                          ▼               ▼               ▼
               │                    Domain Forensics Catalog Depth  Price Anomaly
               │                    (Typosquatting)  (Policy Links) (MSRP Floor)
               │                          │               │               │
               │                          └───────────────┴───────────────┘
               │                                          │
               │                                          ▼
               │                              [ Worker 4: Synthesizer ]
               │                               (3-Tier Risk Hierarchy)
               │                                          │
               └──────────────────────────┬───────────────┘
                                          ▼
                    ┌─────────────────────┴─────────────────────┐
                    │                                           │
         [ Low Risk (Score ≥ 70) ]                  [ High Risk (Score < 45) ]
                    │                                           │
                    ▼                                           ▼
         🟢 APPROVED FOR CAPTURE                    🚨 PHISHING INTERCEPTED
         • Order captures smoothly                  • Payment VOIDED before capture
         • 7-Day cache refreshed                    • Merchant account QUARANTINED
         • Recorded in Audit Log                    • Appeal Ticket & Dossier logged
```

---

## 🛠️ Key Architectural Innovations

1. **Asynchronous Pre-Settlement Hold (`intent: "AUTHORIZE"`)**:
   - The buyer authorizes payment instantly; funds are temporarily placed on authorization hold. The buyer experiences **zero perceived latency**.
2. **7-Day Conditional Verification Caching**:
   - Authorized merchant-website associations are cached for 7 days (`< 5 ms` response time).
   - **Conditionality Rule**: The cache is immediately evicted if lightweight change detection catches alterations in DNS records, TLS certificate thumbprints, or new fraud dispute reports.
3. **Single-Flight Concurrency Deduplication**:
   - If 1,000 customers visit an unverified merchant domain simultaneously, Argus runs the deep crawler **exactly once**, fanning out the result to all waiting requests without overloading the server.
4. **Normalized Entity Decoupling (Merchants ↔ Websites)**:
   - Prevents the *Reseller Spoof Attack*: Verifying a merchant's business identity does not automatically trust every domain they use. Domain authorization is maintained and checked independently.
5. **3-Tier Risk Hierarchy**:
   - **Low Risk (70–100)**: Allow & capture payment.
   - **Medium Risk (45–69)**: Warn buyer; require step-up confirmation.
   - **High-Confidence Fraud (< 45)**: Void hold; quarantine merchant; dispatch incident dossier.
6. **Merchant Grievance & Appeal Resolution System**:
   - Eliminates the "dead-end" problem of automated account bans. Merchants receive an evidence dossier, can raise appeal tickets, and compliance administrators can review and approve appeals live.

---

## 💻 Tech Stack & Sponsor Tools

* **Backend Gateway**: Python 3.11, FastAPI, `concurrent.futures` multi-threaded worker engine.
* **Storage**: SQLite 3 with Write-Ahead Logging (`PRAGMA journal_mode=WAL;`), normalized relational schema.
* **Security & Inspection**: BeautifulSoup4, Pydantic v2, Levenshtein distance typosquatting algorithms.
* **Sponsor Integrations**:
  - **AG Grid**: Powers the enterprise Security Operations Center across 3 responsive, dark-themed data grids (Global Merchant Trust Registry, Audit Ledger, and Merchant Appeals Center) with dynamic column auto-fitting and real-time filtering.
  - **PayPal Developer**: Orders API v2 Two-Phase Settlement (`intent: "AUTHORIZE"` / `CAPTURE` / `VOID`) with automated sandbox credentials management.
  - **Postman**: Full API Collection v2.1.0 (`postman/argus_api_collection.json`) with automated pre-request scripts and test assertions across all endpoints.
  - **Render**: One-click cloud deployment blueprint via `render.yaml` with automated builds and health monitoring.

---

## 📮 API Testing with Postman (Sponsor Integration)

Argus includes an official **Postman Collection v2.1.0** and Environment specification ready for immediate testing.

### 1. Import Files into Postman
1. Open the [Postman Web](https://web.postman.co) or Desktop app.
2. Click **Import** in the top-left corner.
3. Drag & drop the two files located in the `postman/` directory:
   - `postman/argus_api_collection.json` (12 fully documented requests with automated tests)
   - `postman/argus_environment.json` (Pre-configured `{{base_url}}` set to `http://127.0.0.1:8000`)
4. Select the **Argus Local & Cloud Environment** from the environment dropdown.

### 2. Run the Collection Runner
Click **Run Collection** to automatically execute all automated test assertions:
- `Verify Genuine Merchant`: Asserts HTTP 200, `trust_score >= 70`, and `action_taken == "APPROVED_FOR_CAPTURE"`.
- `Verify Phishing Threat`: Asserts HTTP 200, `trust_score < 45`, and `action_taken == "TRANSACTION_VOIDED_AND_ACCOUNT_SEALED"`.
- `PayPal Orders Lifecycle`: Tests `create-order` (intent: `AUTHORIZE`), `capture-order`, and `void-order`.
- `Trust Registry & Cache`: Tests 7-day TTL check and manual cache invalidation.
- `Appeals Workflow`: Submits and resolves merchant dispute tickets live.

*Direct UI Download*: You can also click the **Postman Collection** button in the dashboard navbar to download the JSON directly from the running server.

---

## ☁️ Deploying to Render (Sponsor Integration)

Argus includes a pre-configured [`render.yaml`](file:///x:/hackathon/render.yaml) blueprint specification for seamless cloud deployment.

### Deploy in 3 Steps:
1. Push your repository to GitHub.
2. Log into [dashboard.render.com](https://dashboard.render.com) and click **New +** -> **Blueprint**.
3. Select your repository. Render automatically reads `render.yaml`, provisions the Python 3.11 environment, installs dependencies, and deploys Uvicorn with auto-assigned `$PORT`.

**Environment Variables to set in Render Dashboard:**
- `PAYPAL_CLIENT_ID`: Your PayPal Sandbox Client ID
- `PAYPAL_CLIENT_SECRET`: Your PayPal Sandbox Secret
- `PAYPAL_BASE_URL`: `https://api-m.sandbox.paypal.com`

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.11+ installed.

### 2. Installation
```bash
git clone https://github.com/your-username/argus-trust-gateway.git
cd argus-trust-gateway
python -m pip install -r requirements.txt
```

### 3. Run the Server
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:8000
```

---

## 🧪 Running the Automated Test Suite

We provide a comprehensive test suite validating all core architectural claims:

```bash
# 1. Test 7-Day Caching & Invalidation
python -m tests.test_registry

# 2. Test Single-Flight Concurrency Deduplication (10 concurrent threads -> 1 crawl)
python -m tests.test_single_flight

# 3. Test 3-Tier Risk Mitigation (Nike vs Amazon Phishing)
python -m tests.test_mitigation

# 4. Test Merchant Appeal Lifecycle (Quarantine -> Appeal -> Approved -> Restored)
python -m tests.test_appeals

# 5. Test Full REST API Endpoints
python -m tests.test_server_api
```

---

## 📜 Documentation

- [**`docs/PROJECT_OVERVIEW.md`**](file:///x:/hackathon/PROJECT_OVERVIEW.md): Comprehensive project context, confirmed vs. suggested requirements, pillar boundaries, and award alignment strategy.
- [**`docs/SYSTEM_ARCHITECTURE.md`**](file:///x:/hackathon/SYSTEM_ARCHITECTURE.md): Full architectural diagrams, database ER schemas, data flow, caching rules, and security dilemma analysis.
- [**`docs/IMPLEMENTATION_PLAN.md`**](file:///x:/hackathon/IMPLEMENTATION_PLAN.md): 6-phase engineering plan and checklist.

---

## ⚖️ License
Distributed under the MIT License. Built for the PayPal AI Hackathon 2026.
