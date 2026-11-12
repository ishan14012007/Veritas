# PROJECT OVERVIEW: ARGUS (with Accord & Shared Server Ecosystem)

> **Document Status**: Draft / Awaiting User Approval  
> **Target Event**: PayPal AI Hackathon 2026 (Devpost)  
> **Scope Confirmation**: **We are actively implementing ARGUS and the shared SERVER infrastructure.** (Accord is developed independently by teammate).

---

## 1. Executive Summary

Digital commerce has fundamentally reduced transaction friction, but it has drastically amplified the **cost of mistrust**. When malicious actors exploit checkout payment gateways (such as PayPal's Orders API), they declare trusted, established brand names (e.g., `"Amazon India"`, `"Apple Store"`, `"Nike"`) while pairing them with rogue, lookalike, or disposable domains (e.g., `amaz0n-deals.xyz`). Unsuspecting buyers authorize transactions under the impression that they are paying the legitimate brand.

The resulting fallout is severe: buyers suffer financial loss, legitimate merchants suffer brand erosion, and payment networks bear millions of dollars in customer disputes, chargebacks, and manual arbitration.

**Argus** (formerly TrustShield) is an autonomous, real-time merchant identity verification, domain forensics, and fraud mitigation platform. Designed specifically for PayPal's pre-settlement lifecycle, Argus inspects transaction intent in parallel to eliminate buyer checkout latency, deploys a 3-tier risk mitigation engine with automated quarantines, maintains a persistent Global Merchant Trust Registry with 7-day conditional verification caching, and provides an explainable Merchant Grievance & Appeal System to prevent permanent false-positive account terminations.

---

## 2. The Three System Pillars

The broader platform conceptualized during brainstorming comprises three modular, independently deployable entities:

```
┌────────────────────────────────────────────────────────────────────────┐
│                                PLATFORM                                │
├───────────────────────────────┬────────────────────────────────────────┤
│           ARGUS               │                 ACCORD                 │
│  (Merchant Trust & Security)  │   (Human Agreements & Coordination)    │
│  • Domain & TLD Forensics     │   • Natural Conversation Parsing       │
│  • Catalog & Policy Inspector │   • Formal Agreement Extraction        │
│  • Price Anomaly AI           │   • Payment Obligation Ledger          │
│  • 3-Tier Risk Mitigation     │   • Group Payment Orchestration        │
│  • Merchant Appeals System    │   • (Built independently by teammate)  │
│  • AG Grid Ops Dashboard      │                                        │
└───────────────────────────────┴────────────────────────────────────────┘
                                ▲
                                │ REST APIs
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        SHARED SERVER / BACKEND                         │
│  • Global Merchant Trust Registry                                      │
│  • 7-Day Conditional Verification Cache                                │
│  • Single-Flight Duplicate Job Prevention                              │
│  • Lightweight Change Detection Engine                                 │
│  • Normalized Relational Database (Merchants ↔ Websites)               │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Argus (Our Scope)**: The security, fraud detection, and trust authority. Operates standalone. Can be invoked directly by PayPal checkout webhooks, proxy gateways, or third-party platforms (like Accord).
2. **Accord (Teammate's Scope)**: The conversational intelligence agent (`/startLL` → `/endLL`) that parses human discussions into structured payment commitments.
3. **Server (Shared Core Infrastructure / Our Implementation)**: The shared data layer and verification manager that prevents repetitive AI inspections, manages caching, and coordinates background verification jobs.

---

## 3. Extracted Requirements Matrix

### 3.1 Confirmed Requirements (From Brainstorming)
* **Merchant & Brand Impersonation Detection**: Intercept checkout intent (`brand_name`, `merchant_url`, `product`, `price`) and identify discrepancies between declared brand identity and actual domain ownership.
* **Parallel Asynchronous Verification**: Inspection must execute asynchronously in parallel (< 10 ms fast heuristics, sub-second deep check) so the buyer experiences zero perceived checkout delay.
* **Asynchronous Pre-Settlement Hold (`intent: "AUTHORIZE"`)**: Transaction funds must be placed on temporary authorization hold during verification; funds are only captured if safe, or voided before capture if fraudulent.
* **Global Merchant Trust Registry**: Verified merchants and domains are persisted in a centralized registry so known trustworthy actors do not undergo expensive re-inspections on every visit.
* **7-Day Conditional Verification Caching**: Verification results are reused for 7 days **provided no critical changes have occurred** on the target merchant/domain.
* **Duplicate Verification Prevention (Single-Flight)**: When multiple concurrent requests hit an unverified merchant, only a single verification job executes; results are fanned out to all waiting sessions.
* **Merchant Grievance & Appeals Ticket System**: Legitimate sellers flagged by automated heuristics must not hit a dead-end; they receive an evidence dossier, can raise an appeal ticket, upload documentation, and track investigation.
* **AG Grid Security Operations Dashboard**: Interactive data-management interface utilizing AG Grid to display real-time transaction audit streams, merchant registry records, risk scores, and open appeal tickets (qualifying for the AG Grid Sponsor Prize).
* **PayPal Developer Integration**: Direct integration with PayPal Sandbox Orders API v2.
* **Independent Service Boundary**: Argus must operate completely independently of Accord; it must not depend on Accord's database, runtime, or UI.

### 3.2 Proposed Decisions (Suggestions from Brainstorming requiring formalization)
* **3-Tier Risk Classification vs. Binary Freeze**:
  * *Low Risk*: Allow payment; continue background monitoring.
  * *Medium Risk*: Warn buyer with alert modal; require explicit confirmation or temporary hold.
  * *High-Confidence Fraud*: Immediately void authorization hold; freeze/quarantine merchant account in the local registry; dispatch alert to PayPal Compliance.
* **Two-Speed Inspection Path**:
  * *Fast Path (Synchronous / Gateway)*: Domain forensics, TLD risk lists, Levenshtein typosquatting, cached registry lookup (< 10 ms).
  * *Deep Path (Asynchronous Background)*: HTML scraping, policy verification (Privacy, Terms, Return), catalog depth estimation, and LLM pricing anomaly reasoning.
* **Lightweight Change Detection**: Checking DNS hash, SSL certificate thumbprint, and redirect destination to invalidate the 7-day cache prior to TTL expiry if tampering is detected.

---

## 4. Component Boundaries & Responsibilities

| Component | Responsibility | Boundary / Non-Responsibility |
| :--- | :--- | :--- |
| **Argus Engine** | • Forensic domain and TLD checks<br>• HTML scraping & catalog analysis<br>• Price anomaly evaluation<br>• Risk scoring and evidence compilation | Does NOT manage group chat conversations or parse informal human dialogue. |
| **Argus Dashboard** | • AG Grid transaction monitoring<br>• Merchant trust registry viewer<br>• Appeal ticket processing interface | Does NOT manage payment splits or user debt balances. |
| **Shared Server** | • Normalized database operations<br>• 7-day cache TTL management<br>• Single-flight job queue locking<br>• Change detection hashing | Does NOT perform frontend rendering or client UI logic. |
| **Accord (Teammate)** | • Conversation understanding (`/startLL`, `/endLL`)<br>• Debt calculation and payment coordination | Calls Argus/Server via public REST APIs; has its own separate database. |

---

## 5. Hackathon & Award Track Strategy

To maximize podium finishes across the \$67,500+ prize pool, Argus is structured to qualify across multiple tracks:
1. **Best Use of Agentic Commerce (\$5,000)**: Autonomous risk interception and account quarantine acting as an automated compliance agent.
2. **Most Impactful (\$5,000)**: Measurably eliminates dispute costs and stops brand phishing at checkout.
3. **Best Use of PayPal Tools (\$5,000)**: Direct utilization of PayPal Orders v2 (`AUTHORIZE`, `CAPTURE`, `VOID`).
4. **AG Grid Sponsor Award (Cash Prize)**: Deep integration of AG Grid for the enterprise security dashboard.
