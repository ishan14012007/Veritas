# VERITAS Engineering Task Allocation & Responsibility Matrix

## 1. Product Ownership Summary

| Role / Owner | Product Domain | Primary Responsibilities |
| :--- | :--- | :--- |
| **User (You)** | **ACCORD Lead** | Conversational ingestion, PII scrubbing, Google Gemini prompt orchestration (extraction, splits, ambiguity, queries), two-phase confirmation, decimal-safe split engine, explicit payment requests, and PayPal server capture. |
| **Teammate** | **ARGUS Lead** | Merchant onboarding, independent per-domain authorization, automated security scanning, anti-SSRF defenses, explainable risk scoring, deterministic `payment_allowed` policy, and Gemini risk summarization. |
| **Shared / Joint** | **Core Platform** | Unified database schemas, IAM & RBAC, ARQ async worker with Redis, Google Gemini adapter, PayPal Orders/Invoicing/Capture broker, WhatsApp gateway, and shared frontend shell. |

---

## 2. Itemized Task Breakdown

### 2.1 Shared Core Platform Tasks (Joint Foundation — Core MVP)

| ID | Task Name | Description & Acceptance Criteria |
| :--- | :--- | :--- |
| **CORE-01** | **Database & ARQ Infrastructure** | Docker Compose for PostgreSQL 16 & Redis 7. Creation of schemas `core`, `accord`, `argus`. ARQ worker setup with retry policies and timeouts. |
| **CORE-02** | **IAM, RBAC & Consent** | User registration, login, JWT issuance, refresh tokens, role dependencies, and user WhatsApp opt-in consent tracking. |
| **CORE-03** | **Google Gemini AI Service Adapter** | Provider-independent adapter interface (`BaseAIProvider`) and concrete `GeminiAIAdapter` with structured Pydantic schemas. |
| **CORE-04** | **PayPal Sandbox Platform Broker** | OAuth2 token caching, Orders API, Invoicing API, server-side capture endpoint, and official signature verification via PayPal's API. |
| **CORE-05** | **WhatsApp Cloud Gateway** | Inbound signature verification (`X-Hub-Signature-256`) and template notification dispatcher with `MOCK_WHATSAPP` toggle. |
| **CORE-06** | **Webhook Replay Protection** | Timestamp drift validation ($< 5$ min), Redis distributed locks, and idempotent event logging in `core.webhook_events`. |
| **CORE-07** | **Shared Frontend Shell** | React + Vite + TypeScript + Tailwind layout, navigation switcher between ACCORD and ARGUS, and PayPal JavaScript SDK wrapper. |

---

### 2.2 ACCORD Product Track (Assigned to You / User — Core MVP)

| ID | Task Name | Description & Acceptance Criteria |
| :--- | :--- | :--- |
| **ACC-01** | **Transcript Ingestion & PII Scrubbing** | Endpoint for uploading chat exports (`.txt`) and text. Automated PII scrubbing (card PANs, SSNs) and retention timestamp assignment. |
| **ACC-02** | **Gemini Extraction & Ambiguity Engine** | AI extraction pipeline generating draft agreements, obligations, split suggestions, and ambiguity warnings for vague terms. |
| **ACC-03** | **Natural Language Financial Queries** | Endpoint (`POST /api/v1/accord/agreements/{id}/query`) answering conversational financial queries via Gemini. |
| **ACC-04** | **Two-Phase Confirmation Lifecycle** | Explicit review state machine: `DRAFT` $\to$ `CONFIRMED`. Captures explicit confirmation from participants before payments can be created. |
| **ACC-05** | **Decimal-Safe Split Engine** | Floating-point safe arithmetic (`Decimal`) supporting: Equal, Exact, Percentage, and Shares with penny-adjustment balance distribution. |
| **ACC-06** | **Payment Request & Invoice Generation** | Explicit user action endpoint generating PayPal Sandbox orders/invoices and sending WhatsApp templates to consenting participants. |
| **ACC-07** | **Server-Side Payment Capture** | Checkout reconciliation: debtor authorizes via PayPal JS SDK $\to$ backend calls PayPal capture API to verify amount before marking share as `PAID`. |
| **ACC-08** | **Transcript Deletion & Privacy** | Endpoint (`DELETE /api/v1/accord/conversations/{id}`) enabling Right-to-be-Forgotten deletion of raw and scrubbed text. |
| **ACC-09** | **ACCORD Frontend Views** | Chat uploader, ambiguity review, interactive split matrix, agreement confirmation editor, and PayPal checkout modal. |

---

### 2.3 ARGUS Product Track (Assigned to Teammate — Core MVP)

| ID | Task Name | Description & Acceptance Criteria |
| :--- | :--- | :--- |
| **ARG-01** | **Merchant Registration** | Merchant profile management and basic business identification (`/api/v1/argus/merchants`). |
| **ARG-02** | **Independent Domain Authorization** | Challenge generation (`DNS_TXT`, `HTTPS_META_TAG`) and validation worker ensuring merchants independently authorize every domain. |
| **ARG-03** | **Automated Security Scanner** | ARQ scanning worker inspecting authorized domains: SSL/TLS certificate, security headers (HSTS, CSP), DNSSEC/SPF/DMARC, and Safe Browsing. |
| **ARG-04** | **Anti-SSRF Scanner Sandbox** | Pre-resolution DNS check blocking loopback, RFC 1918 private IPs, and cloud metadata (`169.254.169.254`). Pinned socket connections against DNS rebinding. |
| **ARG-05** | **Explainable Risk Scoring & Policy** | Scoring engine computing `trust_score` ($0-100$), discrete `risk_level` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and `payment_allowed` policy. Rule: TLS alone never proves legitimacy. |
| **ARG-06** | **Gemini Evidence & Risk Summarizer** | Generates plain-English narrative summaries of scan findings and actionable security recommendations. |
| **ARG-07** | **Pre-Checkout Risk Advisory API** | Pre-checkout risk assessment endpoint (`/api/v1/argus/risk/assess`) returning risk level, `payment_allowed`, and evidence rationale. |
| **ARG-08** | **ARGUS Frontend Views** | Merchant profile dashboard, domain verification challenge wizard, and visual security audit report scorecard. |

---

### 2.4 Post-MVP & Optional Tasks (Excluded from Critical MVP Path)

| ID | Feature Name | Description | Target Track |
| :--- | :--- | :--- | :--- |
| **POST-01** | **Embeddable Trust Seal** | JavaScript widget (`seal.js`) and dynamic signed SVG seal for storefronts. | ARGUS Post-MVP |
| **POST-02** | **Merchant Subscription Billing** | Recurring billing for continuous automated security monitoring. | ARGUS Post-MVP |
| **POST-03** | **Advanced KYB Document Verification** | Automated validation against government company registry APIs. | ARGUS Post-MVP |
| **POST-04** | **Audio Note Transcription** | Speech-to-text pipeline for voice note exports. | ACCORD Post-MVP |
| **POST-05** | **Dispute Resolution Portal** | Structured dispute mediation for contested split obligations. | ACCORD Post-MVP |
