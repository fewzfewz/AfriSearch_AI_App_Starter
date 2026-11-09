# AfriSearch AI — Commercial SaaS Product Roadmap

**Document Version:** 1.0.0  
**Status:** Architectural Plan  
**Target Architecture:** Multi-Tenant Commercial SaaS Platform  

---

## 1. Executive Vision & Business Model

AfriSearch AI is transforming into a commercial, multi-tenant B2B and prosumer SaaS platform. The product empowers organizations—universities, research institutes, NGOs, legal practices, clinics, financial institutions, and government agencies—to transform private document repositories into verifiable, multilingual knowledge bases.

### Core Business Model Principles
1. **The Organization is the Paying Customer:** Subscriptions, billing profiles, payment methods, seats, and aggregate quotas belong to the **Organization**.
2. **Workspaces are Collaboration Containers:** Organizations contain multiple workspaces (e.g., "Legal Compliance", "Agronomy Field Research", "Executive Finance"). Workspaces contain documents, tags/folders, and chats.
3. **Multilingual First:** Native support for African languages (Amharic, Swahili, Somali, Hausa, Afaan Oromo) alongside English and French.
4. **Verifiable Citations:** AI answers must be strictly grounded in uploaded source evidence with clickable, verifiable page-level references.
5. **Pan-African Payment Inclusivity:** Frictionless checkout supporting local African payment rails (Telebirr and CBE Birr in Ethiopia, M-Pesa in Kenya, Mobile Money across West Africa) alongside international cards via Stripe.

---

## 2. Product Capability Inventory & Gap Analysis

Each capability is analyzed below with an inspection of the current codebase, reusable components, required API/UI changes, database schema modifications, security requirements, complexity, and priority.

```
Priority Tiers:
- P0: Critical Path (Foundational Multi-Tenant Structure & Core Billing)
- P1: Pilot & Launch Ready (Self-Serve Checkout, Entitlement Enforcement, Invoicing)
- P2: Commercial Scale (Organization Analytics, Advanced RBAC, Local African Payments)
- P3: Enterprise Expansion (SSO, Audit Logs, Custom SLA)
```

---

### Capability 1: User Registration, Login & Account Management

- **Existing Implementation:**
  - Supabase Auth integration in `backend/auth.py` and `web/src/pages/SignInPage.tsx`.
  - Email/password, password reset, and Google OAuth buttons.
  - Verification of access tokens using published JWKS public keys (`ES256`, `RS256`).
  - User sync into SQLite `users` table upon request.
- **Reusable Components:**
  - `backend/auth.py:current_user`, `verify_token`.
  - `web/src/lib/auth.tsx` (AuthContext, Supabase client).
  - `web/src/pages/SignInPage.tsx`.
- **Missing Backend APIs:**
  - `PATCH /api/me` (update user profile: name, avatar, preferred language).
  - `POST /api/me/change-password` (proxied or handled via Supabase).
  - `GET /api/me/organizations` (list organizations the user belongs to).
- **Missing Frontend Screens:**
  - User Profile settings modal/tab in `SettingsPage.tsx`.
  - Onboarding flow: "Create an Organization or join an existing one".
- **Database Changes:**
  - Add `avatar_url TEXT`, `locale TEXT DEFAULT 'en'` to `users` table.
- **Dependencies:** Supabase Auth project credentials.
- **Security Requirements:** Password minimum 8 characters, MFA support via Supabase, rate limiting on auth callback routes.
- **Acceptance Criteria:**
  - New user can register, verify email, log in, and view personal profile.
  - Active session automatically loads the user's default organization and active workspace.
- **Complexity:** Low (S)
- **Priority:** P0

---

### Capability 2: Organization Creation & Ownership

- **Existing Implementation:**
  - None. Current hierarchy jumps directly from `User` to `Workspace`.
- **Reusable Components:**
  - `backend/db.py:connect` transaction pattern.
  - Modal patterns from `web/src/components/ui.tsx`.
- **Missing Backend APIs:**
  - `POST /api/organizations` (create new organization, sets creator as `owner`).
  - `GET /api/organizations/{org_id}` (get organization metadata, plan, member counts).
  - `PATCH /api/organizations/{org_id}` (rename organization, update billing email, tax ID).
  - `DELETE /api/organizations/{org_id}` (delete organization and cascade all workspaces, requires owner confirmation).
  - `GET /api/organizations/{org_id}/members` (list organization-level members and roles).
  - `POST /api/organizations/{org_id}/invitations` (invite member to organization).
- **Missing Frontend Screens:**
  - Organization switcher dropdown in the sidebar (above Workspace switcher).
  - "Create New Organization" modal.
  - "Organization Settings" page with tabs: General, Members & Seats, Billing & Plans, Usage.
- **Database Changes:**
  - New table `organizations` (`id`, `name`, `billing_email`, `owner_id`, `created_at`).
  - New table `organization_members` (`organization_id`, `user_id`, `role` [owner, billing_admin, admin, member], `joined_at`).
  - New table `organization_invitations` (`organization_id`, `email`, `role`, `invited_by`, `created_at`).
- **Dependencies:** User authentication.
- **Security Requirements:**
  - Strict tenant boundary: Users can only query organizations they belong to.
  - Only `owner` can transfer ownership or delete organization.
- **Acceptance Criteria:**
  - User can create an organization, assign a billing contact, and invite organization-level administrators.
  - Deletion cascades cleanly and safely cleans up all child workspaces and files.
- **Complexity:** Medium (M)
- **Priority:** P0

---

### Capability 3: Workspace Creation & Management

- **Existing Implementation:**
  - Workspaces exist (`backend/db.py:create_workspace`, `backend/store.py`).
  - Each workspace has isolated documents under `data/workspaces/<workspace_id>/`.
- **Reusable Components:**
  - DocumentStore isolation in `backend/store.py`.
  - Workspace selector in `web/src/pages/AppLayout.tsx`.
- **Missing Backend APIs:**
  - Update `POST /api/workspaces` to accept `organization_id` (verifying organization plan limits).
  - `GET /api/organizations/{org_id}/workspaces` (list workspaces belonging to organization).
  - `POST /api/workspaces/{workspace_id}/archive` (soft-archive inactive workspaces).
- **Missing Frontend Screens:**
  - Workspace grouping under Organization in sidebar.
  - Workspace list view inside Organization Settings.
- **Database Changes:**
  - Add `organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE` to `workspaces` table.
  - Backward compatibility migration: create default personal organizations for existing workspaces.
- **Dependencies:** Capability 2 (Organizations).
- **Security Requirements:**
  - Workspace must strictly inherit membership and subscription bounds from its parent organization.
- **Acceptance Criteria:**
  - Organization admins can create workspaces up to their subscription plan limit.
  - Deleting a workspace removes its physical folder (`data/workspaces/<id>/`) and frees storage quota for the organization.
- **Complexity:** Low-Medium (S-M)
- **Priority:** P0

---

### Capability 4: Workspace Roles (Owner, Admin, Member, Viewer)

- **Existing Implementation:**
  - Current `members` table has `role CHECK (role IN ('owner', 'member'))`.
  - No granular permission enforcement in document upload, delete, or chat creation.
- **Reusable Components:**
  - `backend/auth.py:current_workspace` dependency.
  - `web/src/pages/SettingsPage.tsx` members table.
- **Missing Backend APIs:**
  - Permission middleware/dependency guards:
    - `@require_role('admin')` for document upload, delete, tagging, and indexing.
    - `@require_role('member')` for chat creation and asking questions.
    - `@require_role('viewer')` for read-only query and viewing shared chats.
  - `PATCH /api/workspaces/{id}/members/{user_id}` (change member workspace role).
- **Missing Frontend Screens:**
  - Role dropdown selector in Workspace Members table (`SettingsPage.tsx`).
  - Read-only UI state for `viewer`: hide "Upload", "Delete", "Edit Tags", and "Re-index" buttons.
- **Database Changes:**
  - Update check constraint: `role IN ('owner', 'admin', 'member', 'viewer')`.
- **Dependencies:** Capabilities 2 & 3.
- **Security Requirements:**
  - Viewers must be strictly blocked from mutating documents or triggering indexing jobs.
- **Acceptance Criteria:**
  - A user with `viewer` role cannot upload files (receives 403 Forbidden).
  - An `admin` can upload documents and manage tags, but cannot delete the workspace.
- **Complexity:** Medium (M)
- **Priority:** P1

---

### Capability 5: Subscription Plans (Free, Pro, Business)

- **Existing Implementation:**
  - Static configuration in `backend/config.py` for workspace quota and rate limits.
  - No database-backed plans.
- **Reusable Components:**
  - Rate limiting logic in `backend/limits.py`.
  - Quota verification in `backend/store.py:save_uploads`.
- **Missing Backend APIs:**
  - `GET /api/plans` (public list of available plans, pricing, quotas, features).
  - `GET /api/organizations/{org_id}/subscription` (current plan, active status, quota limits, current usage).
- **Missing Frontend Screens:**
  - Pricing page / Plan comparison modal in web app.
  - "Subscription & Plan" section in Organization Settings.
- **Database Changes:**
  - New table `subscriptions` (`id`, `organization_id`, `plan_id`, `status`, `provider`, `provider_sub_id`, `current_period_start`, `current_period_end`, `cancel_at_period_end`).
  - Plan definitions stored in code/config (or `plans` table) specifying:
    - `max_seats`
    - `max_workspaces`
    - `max_storage_bytes`
    - `max_documents`
    - `max_cloud_questions_per_month`
    - `allowed_models`
    - `ocr_enabled`
- **Dependencies:** Capability 2 (Organizations).
- **Security Requirements:**
  - Plan limits must be evaluated server-side on every write operation, never trusted from client requests.
- **Acceptance Criteria:**
  - Plans are clearly defined with unambiguous limits:
    - **Free:** 1 seat, 1 workspace, 100 MB storage, 15 docs, 50 AI questions/mo.
    - **Pro:** 5 seats, 5 workspaces, 10 GB storage, 500 docs, 1,500 AI questions/mo.
    - **Business:** 20 seats, unlimited workspaces, 100 GB storage, 10,000 docs, 10,000 AI questions/mo.
- **Complexity:** Medium (M)
- **Priority:** P0

---

### Capability 6: Backend Subscription Entitlement Enforcement

- **Existing Implementation:**
  - Workspace upload quota checked in `backend/store.py:save_uploads`.
  - Rate limits checked in `backend/main.py:prepare_ask`.
- **Reusable Components:**
  - `backend/limits.py:check`.
  - `backend/store.py:bytes_used`.
- **Missing Backend APIs:**
  - Entitlement verification service: `backend/entitlements.py`.
  - Pre-flight checks before:
    - Creating a workspace (`check_workspace_limit`).
    - Adding a team member (`check_seat_limit`).
    - Uploading files (`check_storage_and_doc_limit`).
    - Asking a question with cloud model (`check_monthly_question_limit`).
- **Missing Frontend Screens:**
  - Upgrade prompt modal triggered when quota is reached: "You have used 100% of your document limit. Upgrade to Pro for 500 documents."
- **Database Changes:**
  - Aggregated monthly counter in `organization_usage_cycles`.
- **Dependencies:** Capabilities 2, 5.
- **Security Requirements:**
  - Atomic validation to prevent race conditions (e.g. parallel uploads exceeding quota).
- **Acceptance Criteria:**
  - Uploading a file that would exceed organization storage quota returns 402 Payment Required or 429 Quota Exceeded with an actionable upgrade URL.
  - Adding a member beyond seat limit prompts for seat expansion.
- **Complexity:** Medium (M)
- **Priority:** P0

---

### Capability 7: Usage Metering (Storage, Documents, AI Requests, Tokens)

- **Existing Implementation:**
  - Token tracking in `backend/db.py:record_usage` and `backend/llm.py:Usage`.
  - File byte counting in `backend/store.py:bytes_used`.
- **Reusable Components:**
  - `backend/llm.py:cost_usd`.
  - `backend/db.py:usage` table.
- **Missing Backend APIs:**
  - `GET /api/organizations/{org_id}/usage/summary` (real-time aggregation: storage used, docs count, questions this billing cycle, tokens consumed, estimated AI cost).
  - Background cron/job for rolling billing cycle snapshots.
- **Missing Frontend Screens:**
  - Visual quota progress bars in Organization header and Settings:
    - Storage: `[████████░░] 8.2 GB of 10 GB`
    - AI Questions: `[████░░░░░░] 600 of 1,500`
    - Seats: `3 of 5 active`
- **Database Changes:**
  - Add `organization_id` to `usage` table and create index on `(organization_id, created_at)`.
- **Dependencies:** Capabilities 2, 5, 6.
- **Security Requirements:**
  - Usage queries must be scoped strictly to the caller's organization.
- **Acceptance Criteria:**
  - Every cloud AI request records token counts, model ID, and estimated cost against the parent organization.
  - Document deletions immediately reflect in decremented storage and document counters.
- **Complexity:** Medium (M)
- **Priority:** P1

---

### Capability 8: Subscription Checkout & Payment Integration

- **Existing Implementation:**
  - None.
- **Reusable Components:**
  - Transactional email service (`backend/mailer.py`) for receipt delivery.
- **Missing Backend APIs:**
  - Pluggable billing engine (`backend/billing/`):
    - `POST /api/organizations/{org_id}/billing/checkout` (creates Stripe Checkout Session, Chapa payment link, or Paystack checkout).
    - `POST /api/billing/webhooks/stripe` (handles `checkout.session.completed`, `invoice.payment_succeeded`, etc.).
    - `POST /api/billing/webhooks/chapa` (handles Chapa payment verification).
    - `POST /api/billing/webhooks/paystack` (handles Paystack charge/subscription events).
- **Missing Frontend Screens:**
  - Plan selection checkout redirect button.
  - Payment method selector:
    - International: Card / Google Pay / Apple Pay (Stripe).
    - Ethiopia: Telebirr / CBE Birr (Chapa).
    - Kenya / East Africa: M-Pesa (Paystack / Flutterwave).
  - Checkout success / cancellation return pages (`/billing/success`, `/billing/cancel`).
- **Database Changes:**
  - New table `payment_transactions` (`id`, `organization_id`, `provider`, `transaction_ref`, `amount`, `currency`, `status`, `created_at`).
  - New table `payment_customers` (`organization_id`, `provider`, `customer_id`, `created_at`).
- **Dependencies:** Stripe, Chapa, and/or Paystack merchant accounts.
- **Security Requirements:**
  - Webhook signature verification (`stripe.Webhook.construct_event`, Chapa secret hash).
  - Strict idempotent transaction logging to prevent double-crediting.
  - Zero raw credit card numbers touching AfriSearch servers (PCI-DSS SAQ-A compliant hosted checkout).
- **Acceptance Criteria:**
  - Organization owner completes checkout via Stripe or Telebirr; webhook arrives; subscription table updates to `active`; quotas immediately expand.
- **Complexity:** High (L)
- **Priority:** P1

---

### Capability 9: Subscription Renewal, Cancellation, Upgrades & Downgrades

- **Existing Implementation:**
  - None.
- **Reusable Components:**
  - Mailer notifications in `backend/mailer.py`.
- **Missing Backend APIs:**
  - `POST /api/organizations/{org_id}/billing/portal` (creates Stripe Customer Portal session for updating cards/invoices).
  - `POST /api/organizations/{org_id}/billing/change-plan` (prorated upgrade or end-of-period downgrade).
  - `POST /api/organizations/{org_id}/billing/cancel` (sets `cancel_at_period_end = True`).
  - `POST /api/organizations/{org_id}/billing/resume` (re-activates pending cancellation).
- **Missing Frontend Screens:**
  - "Manage Billing" button linking to customer portal.
  - Downgrade warning dialog: "Downgrading to Free requires reducing storage below 100 MB (currently 4.2 GB)."
  - Grace period banner when payment is past due.
- **Database Changes:**
  - Add `dunning_status TEXT`, `canceled_at TEXT` to `subscriptions`.
- **Dependencies:** Capability 8 (Checkout).
- **Security Requirements:**
  - Only Organization Owner can alter or cancel subscriptions.
- **Acceptance Criteria:**
  - Canceling preserves access until the end of the paid billing period.
  - Failed renewal triggers `past_due` state, emails billing contact, and gives 7-day grace period before restricting AI queries.
- **Complexity:** High (L)
- **Priority:** P1

---

### Capability 10: Billing History & Invoices

- **Existing Implementation:**
  - None.
- **Reusable Components:**
  - Date and currency formatting in `web/src/lib/format.ts`.
- **Missing Backend APIs:**
  - `GET /api/organizations/{org_id}/billing/invoices` (list past invoices with PDF download links).
- **Missing Frontend Screens:**
  - Invoices table in Organization Settings -> Billing (Date, Amount, Status, PDF Receipt Link).
- **Database Changes:**
  - New table `invoices` (`id`, `organization_id`, `provider_invoice_id`, `amount_due`, `amount_paid`, `currency`, `status`, `invoice_pdf_url`, `created_at`).
- **Dependencies:** Capability 8 (Payments).
- **Security Requirements:**
  - Invoices contain billing addresses and names; strictly isolated per organization.
- **Acceptance Criteria:**
  - Successful payments store invoice record and provide downloadable PDF receipts.
- **Complexity:** Low-Medium (S-M)
- **Priority:** P1

---

### Capability 11: Organization-Level Usage Analytics

- **Existing Implementation:**
  - Workspace-level insights in `backend/main.py:insights` and `web/src/pages/InsightsPage.tsx`.
- **Reusable Components:**
  - `InsightsPage.tsx` chart components (`QuestionsChart`, `RatingRing`, `UsageCard`).
  - Aggregation queries in `backend/db.py:insights`, `usage_summary`.
- **Missing Backend APIs:**
  - `GET /api/organizations/{org_id}/insights` (cross-workspace aggregation: total questions, questions per workspace, top queried documents across organization, AI token expenditure by model).
- **Missing Frontend Screens:**
  - Organization Analytics tab with filterable workspace breakdown.
- **Database Changes:**
  - Cross-workspace indexed queries on `usage` and `feedback`.
- **Dependencies:** Capabilities 2, 7.
- **Security Requirements:**
  - Scoped to organization admins and owners.
- **Acceptance Criteria:**
  - Organization leadership can view which workspaces and departments are using AI search most actively and track cumulative costs.
- **Complexity:** Medium (M)
- **Priority:** P2

---

### Capability 12: Platform Administration (Super-Admin)

- **Existing Implementation:**
  - None.
- **Reusable Components:**
  - Table UI and pagination components from `web/src/components/ui.tsx`.
- **Missing Backend APIs:**
  - `/api/admin/*` endpoints guarded by `is_super_admin`:
    - `GET /api/admin/organizations` (list all orgs, plans, MRR, status).
    - `GET /api/admin/users` (list users, sign-in providers, activity).
    - `GET /api/admin/metrics` (platform total documents, indexed vectors, monthly AI expenditure, error rates).
    - `POST /api/admin/organizations/{id}/override-quota` (grant pilot/enterprise custom allowances).
- **Missing Frontend Screens:**
  - `/admin` dashboard restricted to platform administrators.
- **Database Changes:**
  - Add `is_super_admin INTEGER NOT NULL DEFAULT 0` to `users` table.
- **Dependencies:** User authentication.
- **Security Requirements:**
  - Enforce strict role check; never grant super-admin via API parameter.
  - Comprehensive audit logging for all admin actions.
- **Acceptance Criteria:**
  - Platform administrator can inspect tenant health, identify failing indexing jobs, and grant custom quota overrides.
- **Complexity:** Medium-High (M-L)
- **Priority:** P2

---

### Capability 13: Secure Tenant Isolation

- **Existing Implementation:**
  - Multi-tenant directory layout: `data/workspaces/<workspace_id>/`.
  - Database queries filter by `workspace_id`.
- **Reusable Components:**
  - `store.py:workspace_dir` and `db.py` constraints.
- **Missing Backend APIs:**
  - Architectural enforcement: Every database query and file operation must be validated against `organization_id` and `workspace_id`.
- **Missing Frontend Screens:**
  - None.
- **Database Changes:**
  - Add foreign key relationships linking all data to organizations.
- **Dependencies:** Capabilities 2, 3.
- **Security Requirements:**
  - Path traversal defense: `file_path` verification in `store.py`.
  - Cross-tenant vector leakage prevention: vectors must only be queried within the workspace scope.
- **Acceptance Criteria:**
  - Zero probability of User A in Organization X accessing, searching, or citing documents from Organization Y.
- **Complexity:** High (L)
- **Priority:** P0

---

### Capability 14: AI Knowledge Search, Document Processing & Citations

- **Existing Implementation:**
  - Complete and verified: `intfloat/multilingual-e5-small`, `cross-encoder` reranker, Tesseract OCR, office parsers, streaming cited answers, follow-up suggestions, chat titles.
- **Reusable Components:**
  - All of `backend/extract.py`, `backend/models.py`, `backend/answers.py`, `backend/text.py`.
- **Missing Backend APIs:**
  - Model feature flags based on subscription plan (e.g., Free users limited to `gemini-flash` or small models; Pro/Business get `claude-opus-5-5`, `gpt-6.1-sol`).
- **Missing Frontend Screens:**
  - Model lock badge in composer: "Upgrade to Pro to use Claude Opus 5.5".
- **Database Changes:**
  - None.
- **Dependencies:** Existing ML pipeline.
- **Security Requirements:**
  - Prompt injection mitigation and strict grounding checks.
- **Acceptance Criteria:**
  - AI answers cite accurate source tags with page numbers; high relevance maintained across all supported languages.
- **Complexity:** Low (S - building on working foundation)
- **Priority:** P0

---

## 3. Phased Implementation Roadmap

```
+--------------------------------------------------------------------------------------------------+
| PHASE 1: Data Model & Hierarchy (P0)                                                             |
| - Introduce Organizations table and OrganizationMembers table in SQLite                          |
| - Link Workspaces to Organizations with automatic backward-compatibility migration               |
| - Update FastAPI dependencies: current_organization, current_workspace                           |
+--------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+--------------------------------------------------------------------------------------------------+
| PHASE 2: Plans, Entitlements & Metering (P0)                                                     |
| - Define Free, Pro, and Business tier limits                                                     |
| - Implement Entitlement Service (blocking quota overruns on upload, members, and AI queries)    |
| - Real-time Organization usage aggregation API                                                   |
+--------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+--------------------------------------------------------------------------------------------------+
| PHASE 3: Checkout & Payment Integration (P1)                                                     |
| - Stripe Checkout & Customer Portal integration                                                  |
| - Chapa (Telebirr/CBE) integration for Ethiopian organizations                                   |
| - Webhook ingestion pipeline with signature verification and idempotent processing               |
| - Invoicing and receipt ledger                                                                   |
+--------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+--------------------------------------------------------------------------------------------------+
| PHASE 4: UI & Workspace RBAC (P1)                                                                |
| - Organization Settings UI (Members, Billing, Invoices, Usage Meters)                            |
| - Workspace permission tiers (Owner, Admin, Member, Viewer)                                      |
| - Quota upgrade modals and plan comparison page                                                  |
+--------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+--------------------------------------------------------------------------------------------------+
| PHASE 5: Scaling & Cloud Migration (P2)                                                          |
| - Migrate SQLite + NumPy files to PostgreSQL + pgvector + S3 object storage                      |
| - Redis-backed distributed task queue for parallel document indexing                             |
| - Platform Admin Dashboard (/admin)                                                              |
+--------------------------------------------------------------------------------------------------+
```
