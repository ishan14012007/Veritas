# VERITAS Security Architecture & Threat Mitigation Specification

## 1. Threat Modeling (STRIDE Analysis)

| Threat Category | Attack Vector in VERITAS | Architectural Mitigation |
| :--- | :--- | :--- |
| **Spoofing** | • Forged WhatsApp webhook callbacks.<br>• Forged PayPal payment capture events.<br>• Malicious actor claiming a domain they don't own. | • Strict HMAC-SHA256 signature verification (`X-Hub-Signature-256`).<br>• PayPal official signature verification API (`/v1/notifications/verify-webhook-signature`).<br>• Mandatory independent DNS TXT / meta-tag challenge for every domain. |
| **Tampering** | • Malicious user altering split share amounts.<br>• AI hallucinating unauthorized payment amounts.<br>• Client-side claim of payment capture without backend verification. | • Decimal-safe backend arithmetic enforcing $\sum \text{shares} = \text{total}$.<br>• **Deterministic Control Principle:** LLM output is strictly advisory and cannot authorize payments.<br>• Mandatory server-side PayPal order capture (`/v2/checkout/orders/{id}/capture`). |
| **Repudiation** | • A participant denies agreeing to an expense split.<br>• A merchant denies owning a scanned website. | • Immutable audit log (`core.audit_logs`) recording IP, user ID, and timestamp of explicit confirmation.<br>• DNS challenge validation logs proving domain control. |
| **Information Disclosure**| • Unauthorized user viewing private transcripts (IDOR).<br>• Leaking tax IDs or PII to external AI models (Gemini). | • Strict object-level participant authorization checks on all query paths.<br>• Automated PII scrubbing before Gemini API invocation.<br>• Field-level `AES-256-GCM` encryption for tax IDs at rest. |
| **Denial of Service** | • Large transcript upload causing ReDoS.<br>• SSRF exploitation targeting internal infrastructure via the scanner.<br>• Webhook replay flooding. | • Maximum 500 KB transcript payload limit with non-backtracking regex.<br>• ARQ scanner worker with pre-DNS resolution blocking internal & cloud metadata IPs.<br>• Webhook timestamp drift checks and Redis distributed idempotency locks. |
| **Elevation of Privilege**| • Standard user accessing merchant verification audits or administrative tools. | • Enforced FastAPI dependency-based RBAC (`RoleChecker`) on every router. |

---

## 2. Artificial Intelligence Security & Safety Boundaries

### 2.1 The Deterministic Control Principle
> [!CAUTION]
> **LLM outputs must NEVER independently authorize payments, execute captures, alter financial ledgers, or make final security decisions.**
1. **ACCORD Guardrails:**
   - Gemini extractions are classified as **unconfirmed proposals** (`status = 'DRAFT'`).
   - The backend enforces strict Pydantic schema validation. If the LLM generates numbers that do not sum to the total value, the extraction is rejected.
   - Actionable payment requests require explicit human confirmation.
2. **ARGUS Guardrails:**
   - Gemini summarizes scanner findings in human-readable terms.
   - The `trust_score` (0–100), `risk_level` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and `payment_allowed` decision are calculated strictly by deterministic Python evaluation rules.
   - **TLS Policy Rule:** Never treat TLS certificate presence alone as proof of merchant legitimacy. A valid TLS certificate with unverified domain ownership or active malware triggers `risk_level = CRITICAL` and `payment_allowed = False`.

### 2.2 PII Redaction Before AI Ingestion
- Uploaded transcripts pass through a regex sanitization pipeline before reaching the Gemini API:
  - Credit card PANs (Luhn-matching sequences) are masked (`**** **** **** 1234`).
  - Passwords and token patterns are scrubbed.
  - National identity numbers are redacted.
- API keys (`GEMINI_API_KEY`) reside exclusively in backend environment variables and are never transmitted to client browsers.

---

## 3. Webhook Replay Protection & PayPal Official Verification

### 3.1 PayPal Official Webhook Verification Protocol
Webhooks arriving at `/api/v1/webhooks/paypal` must strictly undergo official cryptographic validation:
1. **Timestamp Drift Defense:** The server extracts `PAYPAL-TRANSMISSION-TIME`. If timestamp drift exceeds 300 seconds ($5\text{ minutes}$), the event is rejected immediately as a replay attack.
2. **Official PayPal Signature API Call:** The backend makes a secure server-to-server call to:
   `POST https://api-m.sandbox.paypal.com/v1/notifications/verify-webhook-signature`
   passing the incoming transmission headers (`PAYPAL-AUTH-ALGO`, `PAYPAL-TRANSMISSION-ID`, `PAYPAL-TRANSMISSION-SIG`, `PAYPAL-CERT-URL`), the webhook ID, and the exact raw JSON body.
3. **Distributed Idempotency Lock:**
   - The backend acquires a distributed Redis lock: `webhook_lock:paypal:{event_id}` (TTL: 60s).
   - Inserts into `core.webhook_events` with unique constraint on `(provider, event_id)`.
   - If already recorded, returns `200 OK` with status `DUPLICATE_IGNORED` without re-crediting the balance.

### 3.2 WhatsApp Cloud API Security & Verification
- **HMAC-SHA256 Signature Verification:**
  - In LIVE mode, inbound webhooks strictly validate the `X-Hub-Signature-256` header:
  - Backend computes `HMAC_SHA256(raw_body_bytes, WHATSAPP_APP_SECRET)` using `hmac.compare_digest()` constant-time comparison.
  - Invalid signatures return `403 Forbidden` immediately.
- **Strict Mock vs Live Separation:**
  - When `WHATSAPP_MOCK_MODE=true`, mock simulators are active for local testing.
  - In LIVE mode (`WHATSAPP_PROVIDER=meta`, `WHATSAPP_MOCK_MODE=false`), all mock simulation endpoints (`/mock/inbound`, `/mock/status`) return `403 Forbidden`. The system will never silently fall back from live to mock if credentials fail.
- **Cryptographic Phone Number Binding:**
  - Authenticated identity linking requires explicit confirmation with a cryptographically secure, time-expiring single-use token (`secrets.token_hex(3)`).
  - Cross-account phone hijacking is strictly prevented: a number verified by one account cannot be verified or accessed by another without explicit unlinking.
- **Opt-In & Consent Boundary:**
  - Outbound business notifications require explicit `OPTED_IN` consent status.
  - Unlinking an account marks status `OPTED_OUT` and prevents template dispatches.
- **No Autonomous Agreement or Settlement Actions:**
  - Inbound WhatsApp messages are treated strictly as unverified conversational inputs.
  - Inbound messages claiming "I agree" or "I paid $500" NEVER automatically confirm agreements, create payment requests, or capture PayPal payments. Explicit authenticated human approval and server-side capture remain mandatory.

---

## 4. Server-Side Payment Capture & Reconciliation

1. **Client Authorization Only:** The frontend PayPal JavaScript SDK collects payer authorization (`onApprove`), generating an approved `order_id`.
2. **Mandatory Backend Capture:**
   - The frontend transmits the `order_id` to `POST /api/v1/payments/paypal/capture-order/{order_id}`.
   - The backend invokes PayPal's Capture API (`POST /v2/checkout/orders/{order_id}/capture`).
   - The backend verifies:
     - PayPal capture status is `COMPLETED`.
     - Captured amount and currency strictly match the specific `accord.payment_requests` record and its linked individual `obligation` (not the overall group agreement total).
     - `custom_id` matches the specific split share ID.
   - Only upon exact verification is the individual split share and obligation updated to `PAID`.

---

## 5. Independent Domain Authorization & Anti-SSRF Protection

### 5.1 Independent Domain Authorization
- A merchant cannot scan any arbitrary domain.
- Each domain must prove ownership via a DNS TXT challenge (`_veritas-challenge.<domain>`) or an HTTPS `<meta>` tag before scanning tasks are accepted.

### 5.2 ARQ Scanner Worker Anti-SSRF Architecture
To prevent the scanning worker from being abused to scan internal services, cloud metadata, or local networks:
1. **Pre-Resolution DNS Check:** The scanner resolves the domain's hostname via an external trusted DNS resolver (e.g. Cloudflare `1.1.1.1`).
2. **Denylisted IP Ranges:** The resolved IP address must NOT belong to:
   - `127.0.0.0/8`, `::1` (Loopback)
   - `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (Private RFC 1918)
   - `169.254.0.0/16` (Link-local & AWS/GCP/Azure instance metadata `169.254.169.254`)
   - `100.64.0.0/10`, `fc00::/7`, `fe80::/10` (Carrier NAT / IPv6 Private)
3. **Pinned Socket Handshake:** The scanner creates an HTTP/TLS connection directly to the verified IP, setting TLS SNI (Server Name Indication) and `Host` header to the target domain, eliminating DNS rebinding attacks.
4. **Strict Redirect Validation:** HTTP redirects (`301`, `302`) are followed only after re-resolving and re-validating the destination IP against the denylist.

---

## 6. Transcript Privacy, Access Control, Retention & Deletion

1. **Object-Level Authorization (IDOR Defense):**
   - A user can only view conversations they uploaded.
   - A user can only view agreements where their user ID or phone number is in `accord.agreement_participants`.
   - Cross-tenant access attempts return `403 Forbidden` and are logged to `core.audit_logs`.
2. **Data Retention & Right-to-be-Forgotten:**
   - Raw conversation transcripts are assigned a `retention_until` timestamp (default: 30 days).
   - An ARQ cron worker purges expired raw transcripts automatically.
   - Users can invoke `DELETE /api/v1/accord/conversations/{id}` to immediately purge raw and scrubbed text.
