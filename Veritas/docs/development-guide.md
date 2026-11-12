# VERITAS Local Development & Engineering Guide

## 1. Project Directory Structure

```
Veritas/
├── .gitignore
├── README.md
├── docker-compose.yml          # PostgreSQL 16 & Redis 7
├── docker/
│   └── init-schemas.sql        # Creates core, accord, argus schemas
├── docs/                       # Specifications and blueprints
│   ├── api-contracts.md
│   ├── architecture.md
│   ├── database-schema.md
│   ├── development-guide.md
│   ├── integration-plan.md
│   ├── security-requirements.md
│   └── task-allocation.md
├── backend/                    # Python FastAPI application
│   ├── alembic/                # Database migrations
│   │   ├── versions/
│   │   └── env.py
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI entrypoint
│       ├── config.py           # Pydantic BaseSettings
│       ├── core/               # Shared platform services
│       │   ├── ai/             # Provider-independent AI adapter (Gemini API)
│       │   │   ├── base.py
│       │   │   ├── gemini_adapter.py
│       │   │   └── schemas.py
│       │   ├── auth/           # IAM, JWT, RBAC
│       │   ├── database.py     # SQLAlchemy async engine
│       │   ├── models/         # core.* models
│       │   ├── payments/       # PayPal Sandbox SDK, Invoicing & Capture
│       │   ├── messaging/      # WhatsApp Cloud API client
│       │   ├── security.py     # Cryptography, SSRF checks, rate limits
│       │   ├── tasks/          # ARQ worker & job definitions
│       │   │   ├── worker.py
│       │   │   └── jobs.py
│       │   └── webhooks/       # PayPal & WhatsApp webhook routers
│       ├── accord/             # ACCORD domain (User responsibility)
│       │   ├── models/         # accord.* models
│       │   ├── schemas/        # Pydantic v2 schemas
│       │   ├── routers/        # /api/v1/accord/*
│       │   ├── services/       # Ingestion, NLP parsing, split engine
│       │   └── tests/
│       └── argus/              # ARGUS domain (Teammate responsibility)
│           ├── models/         # argus.* models
│           ├── schemas/        # Pydantic v2 schemas
│           ├── routers/        # /api/v1/argus/*
│           ├── services/       # Domain auth, security scanner, trust scorer
│           └── tests/
└── frontend/                   # React + Vite + TypeScript application
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── tailwind.config.js
    └── src/
        ├── components/
        │   └── payments/       # PayPalButtons wrapper (@paypal/react-paypal-js)
        ├── features/
        │   ├── auth/           # Login, consent, profile
        │   ├── accord/         # Transcript uploader, split editor, approval
        │   └── argus/          # Merchant portal, domain auth, scan viewer
        ├── App.tsx
        └── main.tsx
```

---

## 2. Infrastructure Initialization (Docker Compose)

### 2.1 Starting PostgreSQL 16 & Redis 7
```bash
docker compose up -d
```
Verifies running containers:
```bash
docker compose ps
```

---

## 3. Backend Setup & Configuration

### 3.1 Virtual Environment
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

### 3.2 Environment Variables (`backend/.env`)
```env
# Application Settings
ENVIRONMENT=development
APP_SECRET_KEY=dev-insecure-secret-key-change-in-production-min-32-chars
ENCRYPTION_MASTER_KEY=01234567890123456789012345678901
API_V1_PREFIX=/api/v1
CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173"]

# Database & Cache
DATABASE_URL=postgresql+asyncpg://veritas_user:veritas_dev_password@localhost:5432/veritas_db
REDIS_URL=redis://localhost:6379/0

# JWT Auth
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash

# PayPal Sandbox Developer Platform
PAYPAL_CLIENT_ID=your_sandbox_client_id
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret
PAYPAL_API_BASE=https://api-m.sandbox.paypal.com
PAYPAL_WEBHOOK_ID=your_sandbox_webhook_id
PAYPAL_RECEIVER_ACCOUNT=merchant_sandbox_account@example.com
MOCK_PAYPAL=true

# WhatsApp Cloud Platform (Meta Graph API & Mock)
WHATSAPP_PROVIDER=mock
WHATSAPP_MOCK_MODE=true
MOCK_WHATSAPP=true
WHATSAPP_PHONE_NUMBER_ID=mock_phone_id
WHATSAPP_BUSINESS_ACCOUNT_ID=mock_waba_id
WHATSAPP_ACCESS_TOKEN=mock_access_token
WHATSAPP_APP_SECRET=mock_app_secret
WHATSAPP_VERIFY_TOKEN=veritas_verify_token_dev
WHATSAPP_GRAPH_API_VERSION=v21.0
```

### 3.3 Switching from Mock to Meta Live Cloud API
When Meta developer SMS verification succeeds and production credentials are available:
```bash
WHATSAPP_PROVIDER=meta
WHATSAPP_MOCK_MODE=false
MOCK_WHATSAPP=false
WHATSAPP_PHONE_NUMBER_ID=<Your_Meta_Phone_Number_ID>
WHATSAPP_BUSINESS_ACCOUNT_ID=<Your_Meta_WABA_ID>
WHATSAPP_ACCESS_TOKEN=<Permanent_System_User_Token>
WHATSAPP_APP_SECRET=<Meta_App_Secret>
WHATSAPP_VERIFY_TOKEN=<Your_Custom_Verify_Token>
```
The application will automatically switch to `MetaWhatsAppCloudProvider`, enforcing mandatory HMAC signature validation (`X-Hub-Signature-256`) and rejecting mock simulation endpoints.

### 3.4 Database Migrations
```bash
alembic upgrade head
```

### 3.4 Running the FastAPI Dev Server & ARQ Worker
Open two terminal tabs:
```bash
# Terminal 1: FastAPI API Server
uvicorn app.main:app --reload --port 8000

# Terminal 2: ARQ Background Worker
arq app.core.tasks.worker.WorkerSettings
```
- Interactive Swagger UI: `http://localhost:8000/docs`

> [!NOTE]
> **Custom Dead-Letter Handling:** Because ARQ does not include a native Dead Letter Queue, failed jobs that exhaust their 3 retries trigger the custom `on_job_end` hook in `app.core.tasks.worker`. The failure payload is stored in the Redis stream `veritas:arq:dead_letter_queue` and logged to `core.audit_logs`. To inspect failed jobs in development:
> ```bash
> redis-cli xrange veritas:arq:dead_letter_queue - +
> ```

---

## 4. Frontend Setup & Configuration

```bash
cd frontend
npm install
npm run dev
```
- Access at: `http://localhost:5173`
- Includes `@paypal/react-paypal-js` for rendering official PayPal Sandbox buttons.

---

## 5. End-to-End MVP Demonstration Local Testing Walkthrough

Follow these steps to test the complete integrated flow locally:

1. **Ingest Transcript:**
   - In Swagger or Web UI, upload an exported chat transcript via `POST /api/v1/accord/conversations/upload`.
2. **AI Extraction via Gemini:**
   - Call `POST /api/v1/accord/conversations/{id}/parse`.
   - The ARQ worker invokes Gemini with structured JSON output, generating a draft agreement, obligations, and proposed splits.
3. **Review & Human Confirmation:**
   - Review ambiguity warnings and confirm agreement terms via `POST /api/v1/accord/agreements/{id}/confirm`.
4. **Generate Payment Requests:**
   - Trigger `POST /api/v1/accord/agreements/{id}/generate-payment-requests`.
   - The backend calls PayPal's Orders API (`/v2/checkout/orders`) with `intent: CAPTURE` and dispatches WhatsApp notification templates.
5. **Payer Approval via PayPal JS SDK:**
   - In the frontend checkout drawer, the debtor clicks the PayPal button and authorizes the payment in the Sandbox modal.
6. **Server-Side Capture & Reconciliation:**
   - Frontend `onApprove` calls `POST /api/v1/payments/paypal/capture-order/{order_id}`.
   - The backend invokes PayPal capture, strictly verifies the captured amount and currency match the specific payment request and debtor obligation (not the entire agreement total), and marks the obligation as `PAID`.
7. **Webhook Synchronization:**
   - PayPal Sandbox webhook delivers `PAYMENT.CAPTURE.COMPLETED` to `/api/v1/webhooks/paypal`.
   - The backend validates the signature officially, logs the event idempotently, and reconciles the settlement record.
