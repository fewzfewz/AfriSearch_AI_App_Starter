# AfriSearch AI — Subscription, Billing & Usage Metering Design

**Document Version:** 1.0.0  
**Scope:** Commercial Pricing Tiers, Payment Gateways, Webhook Lifecycles, and Metering Architecture  

---

## 1. Commercial Plan Tier Specifications

AfriSearch AI offers three self-serve tiers and a custom institutional tier. Pricing is established in USD with localized regional currency equivalents for African payment rails.

### Subscription Matrix

| Metric / Feature | Free Tier | Pro Tier | Business Tier | Enterprise Tier |
|---|---|---|---|---|
| **Target Audience** | Students, Solo Researchers | Small Teams, Law Firms, Clinics | Universities, NGOs, Financial Co-ops | Government & Large Enterprises |
| **Base Price (USD)** | $0 / month | $29 / month ($290/year) | $149 / month ($1,490/year) | Contact Sales ($500+/mo) |
| **Ethiopia (ETB - Chapa)** | 0 ETB | ~3,500 ETB / month | ~18,000 ETB / month | Invoiced / Wire |
| **Kenya (KES - Paystack)** | 0 KES | ~3,800 KES / month | ~19,500 KES / month | Invoiced / Wire |
| **Included Seats** | 1 | 5 | 20 | Unlimited / Negotiated |
| **Additional Seats** | N/A | $8 / seat / month | $12 / seat / month | Custom |
| **Workspaces** | 1 | 5 | Unlimited | Unlimited |
| **Storage Allocation** | 100 MB | 10 GB | 100 GB | 1 TB+ |
| **Document Limit** | 15 documents | 500 documents | 10,000 documents | Custom |
| **Monthly AI Queries** | 50 queries | 1,500 queries | 10,000 queries | Custom |
| **Included AI Models** | `gemini-flash`, `qwen-small` | Claude 3.5 Sonnet, GPT-4o, Gemini | Claude Opus 5.5, GPT-6.1, All | Custom Fine-Tuned / Dedicated |
| **OCR Capabilities** | Standard (Rate Limited) | Priority OCR (Amharic, Swahili, Eng) | High-Throughput OCR | Dedicated OCR Cluster |
| **Workspace Roles** | Owner | Owner, Admin, Member | Owner, Admin, Member, Viewer | Custom RBAC + Audit Logs |
| **Export Formats** | Markdown | Markdown, JSON, CSV | Markdown, JSON, CSV, Data Zip | Custom API Integrations |
| **Support SLA** | Community | Standard Email (24h) | Priority Email + WhatsApp (4h) | Dedicated Slack / 24/7 SLA |

---

## 2. Database Schema: Subscriptions, Invoices & Metering

The following relational tables govern subscriptions, billing records, and audit ledgers in SQLite (and are directly portable to PostgreSQL).

```sql
-- 1. Organizations (Top-level billing tenant)
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    billing_email TEXT NOT NULL,
    tax_id TEXT,
    country_code TEXT NOT NULL DEFAULT 'ET', -- ET, KE, NG, US, etc.
    currency TEXT NOT NULL DEFAULT 'USD',    -- USD, ETB, KES, NGN
    owner_id TEXT NOT NULL REFERENCES users (id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Organization Members & Roles
CREATE TABLE IF NOT EXISTS organization_members (
    organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'billing_admin', 'admin', 'member')),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (organization_id, user_id)
);

-- 3. Subscriptions Ledger
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL UNIQUE REFERENCES organizations (id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL CHECK (plan_id IN ('free', 'pro', 'business', 'enterprise')),
    status TEXT NOT NULL CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'unpaid')),
    seats_purchased INTEGER NOT NULL DEFAULT 1,
    provider TEXT NOT NULL CHECK (provider IN ('none', 'stripe', 'chapa', 'paystack', 'manual')),
    provider_customer_id TEXT,
    provider_subscription_id TEXT,
    current_period_start TEXT NOT NULL,
    current_period_end TEXT NOT NULL,
    cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
    canceled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS subscriptions_provider_sub ON subscriptions (provider_subscription_id);

-- 4. Invoices & Receipts
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_invoice_id TEXT,
    amount_due INTEGER NOT NULL,  -- in cents or smallest currency unit
    amount_paid INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL CHECK (status IN ('draft', 'open', 'paid', 'uncollectible', 'void')),
    invoice_pdf_url TEXT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS invoices_org ON invoices (organization_id, created_at);

-- 5. Webhook Idempotency Journal
CREATE TABLE IF NOT EXISTS webhook_events (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('received', 'processing', 'processed', 'failed')),
    error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (provider, event_id)
);

-- 6. Organization Monthly Cycle Snapshots
CREATE TABLE IF NOT EXISTS organization_usage_cycles (
    organization_id TEXT NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    cycle_start TEXT NOT NULL,
    cycle_end TEXT NOT NULL,
    questions_count INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    ai_cost_usd REAL NOT NULL DEFAULT 0.0,
    ocr_pages_count INTEGER NOT NULL DEFAULT 0,
    peak_storage_bytes INTEGER NOT NULL DEFAULT 0,
    peak_documents_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (organization_id, cycle_start)
);
```

---

## 3. Metering Engine & Quota Enforcement Rules

```
+-----------------------------------------------------------------------------------------------+
|                                      METERING ENGINE                                          |
+-----------------------------------------------------------------------------------------------+
|  RESOURCE               | ENFORCEMENT TYPE | ACTION UPON LIMIT REACHED                        |
|-------------------------|------------------|--------------------------------------------------|
|  Storage (Bytes)        | Hard Limit       | 402 Error: Upload rejected; shows upgrade button |
|  Document Count         | Hard Limit       | 402 Error: Upload rejected; shows upgrade button |
|  Member Seats           | Hard Limit       | 403 Error: Invitation blocked; add seat in admin |
|  Workspaces Count       | Hard Limit       | 403 Error: Workspace creation blocked            |
|  Cloud AI Questions     | Soft/Hard Limit  | Alert at 80%/100%. Free blocks; Pro/Biz overage  |
|  Advanced Models (Opus) | Gate Check       | Model disabled with locked icon in composer      |
+-----------------------------------------------------------------------------------------------+
```

### Pre-Flight Verification Implementation (`backend/entitlements.py`)
```python
from fastapi import HTTPException
from backend import db

PLANS = {
    "free": {"storage_bytes": 100 * 1024 * 1024, "docs": 15, "seats": 1, "queries": 50, "models": ["gemini-flash", "qwen-small"]},
    "pro": {"storage_bytes": 10 * 1024 * 1024 * 1024, "docs": 500, "seats": 5, "queries": 1500, "models": ["claude-sonnet", "gpt-4o", "gemini-flash"]},
    "business": {"storage_bytes": 100 * 1024 * 1024 * 1024, "docs": 10000, "seats": 20, "queries": 10000, "models": ["claude-opus-5-5", "gpt-6.1-sol", "gemini-4-argon"]},
}

def verify_upload(org_id: str, new_bytes: int, new_docs_count: int = 1) -> None:
    sub = db.get_organization_subscription(org_id)
    plan = PLANS.get(sub["plan_id"], PLANS["free"])
    
    current_bytes = db.get_organization_storage_bytes(org_id)
    if current_bytes + new_bytes > plan["storage_bytes"]:
        raise HTTPException(
            status_code=402,
            detail=f"Storage limit reached ({plan['storage_bytes'] // (1024*1024)} MB). Upgrade plan to upload more.",
            headers={"X-Upgrade-Required": "storage"}
        )
        
    current_docs = db.get_organization_document_count(org_id)
    if current_docs + new_docs_count > plan["docs"]:
        raise HTTPException(
            status_code=402,
            detail=f"Document limit reached ({plan['docs']} documents). Upgrade plan to upload more.",
            headers={"X-Upgrade-Required": "documents"}
        )

def verify_ai_query(org_id: str, model_id: str) -> None:
    sub = db.get_organization_subscription(org_id)
    plan = PLANS.get(sub["plan_id"], PLANS["free"])
    
    # 1. Model accessibility check
    if model_id not in plan["models"]:
        raise HTTPException(
            status_code=403,
            detail=f"Model '{model_id}' requires the Pro or Business plan.",
            headers={"X-Upgrade-Required": "model"}
        )
        
    # 2. Monthly volume check
    cycle_queries = db.get_cycle_query_count(org_id, sub["current_period_start"])
    if cycle_queries >= plan["queries"]:
        if sub["plan_id"] == "free":
            raise HTTPException(
                status_code=402,
                detail=f"Free monthly AI query limit reached ({plan['queries']}). Upgrade to continue asking.",
                headers={"X-Upgrade-Required": "queries"}
            )
        # Pro/Business: Allow if pay-as-you-go overages are enabled, otherwise halt
```

---

## 4. Payment Gateway Integration Details

AfriSearch utilizes a multi-gateway routing architecture based on the customer's organization billing country.

```
Organization Country Selection
         |
         +---> Ethiopia (ET) ------------> Chapa Gateway (Telebirr, CBE Birr, Awash)
         |
         +---> Kenya (KE) / Nigeria -----> Paystack Gateway (M-Pesa, Card, Bank)
         |
         +---> All Other / International -> Stripe Gateway (Visa, MC, Amex, Apple Pay)
```

### 1. Stripe Integration (Global)
- **API Version:** 2024-06-20
- **Checkout Type:** Stripe Hosted Checkout Session (`mode='subscription'`).
- **Customer Portal:** Stripe Customer Portal for self-service card update, VAT invoice download, and cancellation.
- **Key Webhooks:**
  - `checkout.session.completed`: Maps `client_reference_id` (Org ID) to customer and activates subscription.
  - `invoice.payment_succeeded`: Advances `current_period_end` by 30 days / 365 days.
  - `invoice.payment_failed`: Marks subscription `past_due`; initiates Stripe Smart Retries.
  - `customer.subscription.deleted`: Sets subscription status `canceled`.

### 2. Chapa Integration (Ethiopia)
- **Primary Rail:** Telebirr, CBE Birr, Awash Bank, HelloCash.
- **Checkout Flow:**
  - Backend sends `POST https://api.chapa.co/v1/transaction/initialize` with amount in ETB, `currency="ETB"`, `callback_url`, and custom metadata `{"organization_id": org_id, "plan_id": plan_id}`.
  - User is redirected to Chapa's checkout page to enter their Telebirr phone number or mobile banking PIN.
- **Verification Flow:**
  - Chapa redirects back to `/api/billing/return/chapa?trx_ref=...`.
  - Backend verifies via `GET https://api.chapa.co/v1/transaction/verify/{trx_ref}` and Chapa webhook HMAC signature.
  - Note on Recurring: Since Telebirr does not currently support automated card-less direct debit recurring mandates, subscriptions are handled as 30-day fixed periods with renewal prompt emails 5 days before expiration.

### 3. Paystack Integration (Kenya, Nigeria, Ghana)
- **Primary Rail:** M-Pesa (Kenya), Card, Bank Transfer (Nigeria), Mobile Money (Ghana).
- **Checkout Flow:**
  - Backend creates a Paystack Plan: `POST https://api.paystack.co/plan`.
  - Backend initializes transaction: `POST https://api.paystack.co/transaction/initialize` specifying plan code.
  - User authorizes payment (via M-Pesa STK push prompt on mobile phone).
- **Key Webhooks:**
  - `subscription.create`: Subscription active.
  - `invoice.create` & `invoice.update`: Successful recurring charge.
  - `subscription.disable`: Subscription canceled.

---

## 5. Webhook Processing & Fault Tolerance Pipeline

To guarantee financial integrity, webhook handling implements five defense layers:

1. **Raw Payload Signature Verification:**
   - Raw bytes must be verified before JSON parsing.
   - Stripe: `stripe.Webhook.construct_event(payload, sig, endpoint_secret)`.
   - Chapa: `hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()`.
   - Paystack: `hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()`.
2. **Idempotency Guard (`webhook_events` table):**
   - Unique constraint on `(provider, event_id)`.
   - If an event ID already exists in `webhook_events`, immediately return `HTTP 200 OK` without re-executing logic.
3. **Database Transaction Isolation:**
   - All subscription updates and invoice insertions occur inside a single atomic `BEGIN ... COMMIT` block.
4. **Dunning & Grace Periods:**
   - On payment failure, the subscription is not immediately terminated.
   - Status transitions to `past_due` with a **7-day grace period**.
   - Transactional email sent to `billing_email`: "Your AfriSearch AI subscription renewal failed. Please update your payment method within 7 days to avoid service interruption."
5. **Proration on Plan Changes:**
   - Upgrades take effect immediately; Stripe automatically calculates prorated charges.
   - Downgrades are queued to take effect at the end of the billing period (`cancel_at_period_end = 1`).

---

## 6. Organization-Level Analytics Dashboard Design

The Organization Usage Dashboard provides financial controllers and department heads with transparent operational visibility into their AI expenditure and resource allocation.

```
+-----------------------------------------------------------------------------------------------+
|  ORGANIZATION ANALYTICS: "Addis Ababa Health Institute"                     [ Month: Nov 2026 ]|
+-----------------------------------------------------------------------------------------------+
|  STORAGE CONSUMPTION                |  MONTHLY AI QUESTIONS         |  ACTIVE TEAM SEATS      |
|  [██████████████░░░░░░] 7.2 / 10 GB |  [████████░░░░░░░░░░] 780 / 1500|  4 of 5 seats used      |
|  72% Quota utilized                 |  52% Allocation used          |  1 invite pending       |
+-----------------------------------------------------------------------------------------------+
|  EXPENDITURE BY MODEL                                                                         |
|  - Claude 3.5 Sonnet: 520 queries · 1.4M tokens · $4.20                                       |
|  - GPT-4o:            210 queries · 650k tokens · $1.85                                       |
|  - Gemini 4 Argon:     50 queries · 120k tokens · $0.40                                       |
|  Total AI Infrastructure Cost: $6.45                                                          |
+-----------------------------------------------------------------------------------------------+
|  USAGE BREAKDOWN BY WORKSPACE                                                                 |
|  Workspace                  | Documents | Passages | Questions | Top Language                 |
|  ---------------------------|-----------|----------|-----------|------------------------------|
|  1. Malaria Protocols       | 142       | 3,120    | 480       | Amharic (አማርኛ)              |
|  2. Clinic Financials       | 38        | 840      | 210       | English                      |
|  3. Regional Outreach       | 19        | 410      | 90        | Swahili (Kiswahili)          |
+-----------------------------------------------------------------------------------------------+
```

### Analytics API Endpoint: `GET /api/organizations/{org_id}/analytics`
- **Output Payload:**
  - `period`: start and end timestamps.
  - `summary`: total storage, document count, query count, total tokens, total estimated cost.
  - `workspaces`: breakdown per workspace (docs, bytes, queries, most queried tags).
  - `models`: breakdown per AI model (tokens in, tokens out, estimated provider cost).
  - `languages`: question language distribution (English, Amharic, Swahili, Somali, Oromo).
