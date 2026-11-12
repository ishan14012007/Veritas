# VERITAS API Contracts & OpenAPI Specifications

## 1. Global API Standards

- **Base Endpoint:** `/api/v1`
- **Protocol:** HTTPS (TLS 1.3 preferred)
- **Serialization:** JSON (`application/json`)
- **Authentication:** Bearer JWT in the `Authorization: Bearer <token>` header.
- **Idempotency:** Mutating operations (`POST`, `PUT`) accept an `Idempotency-Key: <UUID>` header.
- **Date-Time Format:** ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).
- **Monetary Quantities:** Sent as string or fixed decimal (`"124.50"`) with explicit 3-letter currency code (`USD`).

---

## 2. Shared Core API Endpoints

### 2.1 Authentication & Consent (`/api/v1/auth`, `/api/v1/users`)

#### `POST /api/v1/auth/register`
- **Request:**
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "full_name": "Jordan Hayes",
    "phone_number": "+14155552671",
    "whatsapp_opt_in": true
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "success": true,
    "data": {
      "user_id": "c1f7a4d2-3a87-4b16-92cf-15e8489d81e0",
      "email": "user@example.com",
      "full_name": "Jordan Hayes",
      "role": "USER",
      "whatsapp_opt_in": true,
      "access_token": "eyJhbGciOi...",
      "refresh_token": "d8e3b1c9...",
      "token_type": "Bearer",
      "expires_in": 900
    }
  }
  ```

#### `POST /api/v1/users/whatsapp-opt-in`
Explicitly records or revokes user consent for WhatsApp notifications.
- **Request:** `{"opt_in": true}`
- **Response (200 OK):** `{"success": true, "data": {"whatsapp_opt_in": true, "updated_at": "2026-11-06T12:00:00Z"}}`

---

### 2.2 Payment Gateway (PayPal Developer Platform) (`/api/v1/payments`)

#### `POST /api/v1/payments/paypal/create-order`
Creates a PayPal Sandbox order linked to a confirmed split share for the frontend PayPal JavaScript SDK.
- **Headers:** `Idempotency-Key: 7b812a44-0a44-42b7-bdc1-84e91244e890`
- **Request:**
  ```json
  {
    "split_share_id": "9d8f3e21-0a44-42b7-bdc1-84e91244e890",
    "amount": "85.00",
    "currency": "USD",
    "description": "ACCORD Split - Lake Tahoe Cabin Rental"
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "success": true,
    "data": {
      "payment_id": "fa910d52-25e1-4569-8db2-23c8a91bca72",
      "paypal_order_id": "8XY12948AB918234",
      "status": "CREATED",
      "amount": "85.00",
      "currency": "USD"
    }
  }
  ```

#### `POST /api/v1/payments/paypal/capture-order/{order_id}`
Executes server-side payment capture after payer approval via the frontend PayPal JS SDK `onApprove`.
- **Validation:** The backend verifies that captured amount and currency match the specific `accord.payment_requests` record and its linked individual `obligation` (not the overall group agreement total).
- **Headers:** `Idempotency-Key: 3c981a2e-5f11-4712-a129-9e81bca91204`
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "data": {
      "payment_id": "fa910d52-25e1-4569-8db2-23c8a91bca72",
      "paypal_capture_id": "981248109247192",
      "status": "CAPTURED",
      "amount_captured": "85.00",
      "currency": "USD",
      "captured_at": "2026-11-06T12:05:00Z"
    }
  }
  ```

---

### 2.3 Shared Webhooks (`/api/v1/webhooks`)

#### `POST /api/v1/webhooks/paypal`
Receives PayPal event callbacks (e.g. `PAYMENT.CAPTURE.COMPLETED`).
- **Official Verification:** Invokes PayPal's official API `POST https://api-m.sandbox.paypal.com/v1/notifications/verify-webhook-signature`.
- **Replay Protection & Idempotency:** Validates timestamp drift ($< 300\text{s}$) and dedupes on `(provider, event_id)` with a Redis lock.
- **Response (200 OK):** `{"status": "EVENT_PROCESSED"}` or `{"status": "DUPLICATE_IGNORED"}`.

#### `GET /api/v1/webhooks/whatsapp`
Meta handshake challenge verification (`hub.mode`, `hub.verify_token`, `hub.challenge`).

#### `POST /api/v1/webhooks/whatsapp`
Receives inbound WhatsApp customer service messages and template button clicks.
- Validates `X-Hub-Signature-256` HMAC.

---

### 2.4 Asynchronous ARQ Job Status (`/api/v1/jobs`)

#### `GET /api/v1/jobs/{job_id}`
Polls or monitors background job status (AI extraction, security scan).
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "data": {
      "job_id": "extract:e4a2d3c1:v1",
      "status": "COMPLETED", // "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED"
      "result": { "agreement_id": "3b29c5a2-9b2f-48d9-8134-8c81b244d567" },
      "error": null,
      "enqueue_time": "2026-11-06T12:01:00Z"
    }
  }
  ```

---

## 3. ACCORD API Contracts (User Responsibility)

### 3.1 Transcript Ingestion & AI Extraction (`/api/v1/accord/conversations`)

#### `POST /api/v1/accord/conversations/upload`
Uploads a chat export (`.txt`) or text transcript.
- **Request (JSON or multipart):**
  ```json
  {
    "title": "Road Trip to Tahoe",
    "source_type": "EXPORT_TXT",
    "raw_transcript": "[11/04/26, 14:22] Alice: Total lodging was $600. Bob owes $200, Charlie owes $200 and I pay $200.\n[11/04/26, 14:25] Bob: Confirmed, I'll pay Friday."
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "success": true,
    "data": {
      "conversation_id": "e4a2d3c1-7b89-4251-b93d-d5a23bca8891",
      "parsing_status": "PENDING",
      "retention_until": "2026-12-06T12:00:00Z"
    }
  }
  ```

#### `POST /api/v1/accord/conversations/{id}/parse`
Triggers Gemini AI extraction on scrubbed transcript. Returns draft agreement with ambiguity warnings.
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "data": {
      "conversation_id": "e4a2d3c1-7b89-4251-b93d-d5a23bca8891",
      "ai_model": "gemini-1.5-flash",
      "draft_agreement": {
        "title": "Road Trip to Tahoe Lodging",
        "summary": "Alice covered $600 for lodging. Bob and Charlie agreed to reimburse $200 each.",
        "total_value": "600.00",
        "currency": "USD",
        "status": "DRAFT",
        "participants": [
          {"name": "Alice", "role": "CREDITOR", "phone_number": "+14155550101"},
          {"name": "Bob", "role": "DEBTOR", "phone_number": "+14155550102"},
          {"name": "Charlie", "role": "DEBTOR", "phone_number": "+14155550103"}
        ],
        "obligations": [
          {"debtor": "Bob", "creditor": "Alice", "amount": "200.00", "currency": "USD", "due_date": "2026-11-07T23:59:59Z", "title": "Lodging reimbursement"}
        ],
        "expense_split": {
          "split_method": "EQUAL",
          "total_amount": "600.00",
          "shares": [
            {"participant_name": "Alice", "amount": "200.00", "is_paid": true},
            {"participant_name": "Bob", "amount": "200.00", "is_paid": false},
            {"participant_name": "Charlie", "amount": "200.00", "is_paid": false}
          ]
        },
        "ambiguity_warnings": [
          {"field": "Charlie due_date", "issue": "No explicit deadline mentioned by Charlie in the chat transcript."}
        ]
      }
    }
  }
  ```

#### `POST /api/v1/accord/agreements/{id}/query`
Allows users to ask natural-language financial queries against the agreement.
- **Request:** `{"query": "How much does Charlie owe in total, and what was it for?"}`
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "data": {
      "answer": "Charlie owes Alice $200.00 for his share of the lodging.",
      "referenced_obligations": ["obl-charlie-lodging-200"]
    }
  }
  ```

#### `DELETE /api/v1/accord/conversations/{id}`
Purges raw and scrubbed conversation text upon user request (Right-to-be-Forgotten).

---

### 3.2 Agreements, Invoices & Payment Requests (`/api/v1/accord/agreements`)

#### `POST /api/v1/accord/agreements/{id}/confirm`
Participant confirmation of agreement terms. Actionable payments require explicit confirmation.
- **Request:** `{"confirmed": true, "notes": "Confirmed."}`
- **Response (200 OK):** Updates participant status; transitions agreement to `CONFIRMED` when all approve.

#### `POST /api/v1/accord/agreements/{id}/generate-payment-requests`
Explicit user action that generates PayPal Sandbox payment links and sends WhatsApp templates to consenting participants.
- **Request:** `{"include_whatsapp_notification": true}`
- **Response (201 Created):**
  ```json
  {
    "success": true,
    "data": {
      "payment_requests_created": 2,
      "requests": [
        {
          "split_share_id": "9d8f3e21-0a44-42b7-bdc1-84e91244e890",
          "payer_phone": "+14155550102",
          "amount": "200.00",
          "currency": "USD",
          "paypal_order_id": "8XY12948AB918234",
          "whatsapp_notification_status": "SENT"
        }
      ]
    }
  }
  ```

#### `POST /api/v1/accord/agreements/{id}/invoices`
Creates a formal milestone invoice via the PayPal Invoicing API.
- **Request:**
  ```json
  {
    "recipient_email": "client@example.com",
    "invoice_number": "INV-2026-001",
    "amount": "1200.00",
    "currency": "USD",
    "due_date": "2026-11-20T00:00:00Z",
    "items": [
      {"name": "Frontend Milestone 1", "quantity": 1, "unit_amount": "1200.00"}
    ]
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "success": true,
    "data": {
      "invoice_id": "INV2-9A82-1249-1092",
      "status": "SENT",
      "payment_url": "https://www.sandbox.paypal.com/invoice/p/#INV2-9A82-1249-1092"
    }
  }
  ```

---

## 4. ARGUS API Contracts (Teammate Responsibility)

### 4.1 Merchant Onboarding & Independent Domain Authorization (`/api/v1/argus/merchants`, `/api/v1/argus/domains`)

#### `POST /api/v1/argus/merchants`
Registers a merchant profile.
- **Request:** `{"business_name": "Apex Outfitters LLC", "business_registration_no": "US-DE-829104", "country_code": "USA"}`
- **Response (201 Created):** Returns generated `merchant_id`.

#### `POST /api/v1/argus/merchants/{merchant_id}/domains`
Registers an independent domain requiring domain-level challenge verification.
- **Request:** `{"domain_name": "shop.apexoutfitters.com", "challenge_type": "DNS_TXT"}`
- **Response (201 Created):** Returns `domain_id` and DNS challenge token (`_veritas-challenge.<domain>`).

#### `POST /api/v1/argus/domains/{domain_id}/verify`
Enqueues ARQ verification job to validate DNS TXT record or HTTPS meta-tag challenge.
- **Response (200 OK):** `{"success": true, "data": {"domain_id": "...", "authorization_status": "VERIFIED"}}`

---

### 4.2 Website Security Scanning (`/api/v1/argus/domains/{domain_id}/scans`)

#### `POST /api/v1/argus/domains/{domain_id}/scans/trigger`
Queues an ARQ security scan for an **authorized** domain.
- **Response (202 Accepted):** `{"success": true, "data": {"scan_id": "3c981a2e-5f11-4712-a129-9e81bca91204", "status": "QUEUED"}}`

#### `GET /api/v1/argus/domains/{domain_id}/scans/{scan_id}`
Returns scan findings for SSL/TLS, security headers, DNSSEC/SPF/DMARC, and Safe Browsing.

---

### 4.3 Explainable Trust Scoring & Pre-Checkout Risk Advisory (`/api/v1/argus/domains/{domain_id}/trust-score`, `/api/v1/argus/risk/assess`)

#### `GET /api/v1/argus/domains/{domain_id}/trust-score`
Returns the explainable risk assessment index ($0-100$), discrete risk level, explicit `payment_allowed` policy decision, and Gemini-generated plain-English explanation.
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "data": {
      "domain_name": "shop.apexoutfitters.com",
      "trust_score": 88.00,
      "risk_level": "LOW",
      "payment_allowed": true,
      "evidence": [
        {"factor": "Domain Ownership Authorized", "points": 25, "status": "PASS", "evidence": "DNS TXT record validated."},
        {"factor": "TLS 1.3 & Valid Certificate", "points": 25, "status": "PASS", "evidence": "Let's Encrypt Authority, 78 days validity."},
        {"factor": "Security Headers (HSTS, CSP)", "points": 15, "status": "PARTIAL", "evidence": "HSTS enabled with preload; CSP header missing."},
        {"factor": "DNS Security (SPF, DMARC)", "points": 10, "status": "PASS", "evidence": "SPF and DMARC records correctly configured."},
        {"factor": "Malware & Safe Browsing Standing", "points": 13, "status": "PASS", "evidence": "Clean standing on Google Safe Browsing."}
      ],
      "ai_summary": "Apex Outfitters demonstrates a strong security posture with verified domain ownership and modern TLS 1.3 encryption. Adding a Content Security Policy (CSP) header would further harden their storefront.",
      "valid_until": "2026-11-13T12:00:00Z"
    }
  }
  ```

#### `POST /api/v1/argus/risk/assess`
Pre-checkout risk evaluation endpoint called by ACCORD or external checkouts.
- **Request:**
  ```json
  {
    "domain_name": "shop.apexoutfitters.com",
    "transaction_amount": "250.00",
    "currency": "USD"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "data": {
      "risk_level": "LOW",
      "payment_allowed": true,
      "trust_score": 88.00,
      "evidence_summary": [
        "Domain ownership verified via DNS TXT challenge.",
        "TLS 1.3 encryption verified with clean malware reputation."
      ]
    }
  }
  ```

---

### 4.4 Embeddable Trust Seal [Post-MVP / Optional] (`/api/v1/argus/badges/{key}/embed`)

---

## 5. ACCORD WhatsApp Business Cloud Platform APIs (`/api/v1/whatsapp/*`)

### 5.1 System Status & Webhook Subscriptions

#### `GET /api/v1/whatsapp/status`
Returns high-level status of WhatsApp integration, active provider (mock/meta), linked accounts, and registered message templates.
- **Headers:** `Authorization: Bearer <jwt>`
- **Response (200 OK):**
  ```json
  {
    "provider": "mock",
    "mock_mode": true,
    "phone_number_id": "mock_phone_id",
    "webhook_url": "/api/v1/whatsapp/webhook",
    "linked_accounts_count": 3,
    "total_messages_count": 14,
    "registered_templates": [
      "accord_agreement_review_v1",
      "accord_consensus_confirmed_v1",
      "accord_payment_request_v1",
      "accord_payment_received_v1",
      "accord_settlement_completed_v1"
    ]
  }
  ```

#### `GET /api/v1/whatsapp/webhook`
Meta WhatsApp Webhook subscription verification handshake (GET challenge).
- **Query Params:** `hub.mode=subscribe`, `hub.verify_token=<token>`, `hub.challenge=<challenge>`
- **Response (200 OK):** `<challenge>` (text/plain)

#### `POST /api/v1/whatsapp/webhook`
Meta WhatsApp Webhook ingestion endpoint for inbound messages and delivery statuses.
- **Headers:** `X-Hub-Signature-256: sha256=<hmac>` (mandatory and verified in LIVE mode)
- **Response (200 OK):** `{"status": "ok", "event_id": "<uuid>", "signature_verified": true}`

### 5.2 Phone Number Linking & Verification

#### `POST /api/v1/whatsapp/accounts/link`
Initiate linking an authenticated VERITAS user account to a WhatsApp phone number.
- **Headers:** `Authorization: Bearer <jwt>`
- **Request Body:**
  ```json
  {
    "phone_number": "+14155550199",
    "display_name": "Charlie Mobile"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "id": "e9a0c102-1234-4567-89ab-cdef01234567",
    "phone_number": "+14155550199",
    "display_name": "Charlie Mobile",
    "connection_status": "PENDING_VERIFICATION",
    "consent_status": "OPTED_OUT",
    "verification_token": "492018"
  }
  ```

#### `POST /api/v1/whatsapp/accounts/verify`
Confirm ownership of linked WhatsApp number using single-use verification code.
- **Headers:** `Authorization: Bearer <jwt>`
- **Request Body:**
  ```json
  {
    "phone_number": "+14155550199",
    "verification_token": "492018"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "id": "e9a0c102-1234-4567-89ab-cdef01234567",
    "phone_number": "+14155550199",
    "connection_status": "CONNECTED",
    "consent_status": "OPTED_IN",
    "verified_at": "2026-11-06T23:50:00Z"
  }
  ```

#### `GET /api/v1/whatsapp/accounts`
List all linked WhatsApp numbers for the authenticated user.
- **Headers:** `Authorization: Bearer <jwt>`

#### `DELETE /api/v1/whatsapp/accounts/{id}`
Unlink and opt-out a connected WhatsApp account.
- **Headers:** `Authorization: Bearer <jwt>`

### 5.3 Messaging & Notifications

#### `POST /api/v1/whatsapp/messages/send`
Dispatch an outbound text or approved template message.
- **Headers:** `Authorization: Bearer <jwt>`
- **Request Body:**
  ```json
  {
    "recipient_number": "+14155550199",
    "message_type": "TEMPLATE",
    "template_name": "accord_agreement_review_v1"
  }
  ```

#### `GET /api/v1/whatsapp/messages`
Query message history for authorized conversations or linked phone numbers.
- **Headers:** `Authorization: Bearer <jwt>`

### 5.4 Test Bench Simulators (MOCK MODE ONLY)

#### `POST /api/v1/whatsapp/mock/inbound`
Simulate an incoming WhatsApp message (strictly forbidden returning 403 in LIVE mode).
- **Headers:** `Authorization: Bearer <jwt>`
- **Request Body:**
  ```json
  {
    "from_number": "+14155550199",
    "content": "Bob paid $450. Alice paid $180.",
    "trigger_analysis": true
  }
  ```

#### `POST /api/v1/whatsapp/mock/status`
Simulate status progression (SENT $\to$ DELIVERED $\to$ READ $\to$ FAILED) (forbidden in LIVE mode).
- **Headers:** `Authorization: Bearer <jwt>`
- **Request Body:**
  ```json
  {
    "provider_message_id": "wamid.MOCK_1234",
    "status": "DELIVERED"
  }
  ```
Public script and SVG rendering endpoints for storefront seals. Excluded from the MVP delivery timeline.
