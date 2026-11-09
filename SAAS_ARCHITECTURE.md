# AfriSearch AI — Commercial SaaS System Architecture

**Document Version:** 1.0.0  
**Architectural Scope:** Multi-Tenant SaaS Architecture, Security, Scaling & Migration  

---

## 1. Domain Entity Hierarchy & Data Ownership Model

The architectural domain follows a strict hierarchical multi-tenant structure designed for B2B contracts, institutional subscriptions, and team collaboration.

```
+-----------------------------------------------------------------------------------------+
|                                    PLATFORM TENANT                                      |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                             ORGANIZATION (Billing Account)                              |
| - Owns: Subscriptions, Invoices, Payment Methods, Aggregate Quotas (Storage, AI tokens) |
| - Contains: Organization Members (Owner, Billing Admin, Admin, Member)                  |
+-----------------------------------------------------------------------------------------+
                                             | 1 : N
                                             v
+-----------------------------------------------------------------------------------------+
|                               WORKSPACE (Project Container)                             |
| - Sub-unit of an Organization (e.g. Legal, Finance, Agronomy Field Research)            |
| - Contains: Workspace Members with RBAC (Owner, Admin, Member, Viewer)                  |
+-----------------------------------------------------------------------------------------+
                        | 1 : N                                            | 1 : N
                        v                                                  v
+---------------------------------------------+     +-------------------------------------+
|                  DOCUMENTS                  |     |                CHATS                |
| - Uploaded Files (PDF, Office, Images)      |     | - Conversation History              |
| - Semantic Embeddings & Text Chunks         |     | - Cited Messages & Explanations     |
| - Metadata, Folders & Tags                  |     | - Feedback Ratings (Thumbs up/down) |
+---------------------------------------------+     +-------------------------------------+
```

### Data Ownership Rules

1. **Organization as Legal & Financial Anchor:**
   - All intellectual property (uploaded documents, extracted passages, chat history) legally belongs to the **Organization**, not individual employee accounts.
   - If an employee leaves the company and their user account is deleted, the organization's workspaces, documents, and historical chats remain intact.
2. **Workspaces as Scoped Collaboration Contexts:**
   - Documents and search indices belong to exactly one workspace.
   - Vector similarity search (`store.py:retrieve`) executes strictly within the scope of a single workspace (or filtered sub-tags within that workspace). Chunks from Workspace A are never indexed into or searched from Workspace B.
3. **User Identity Isolation:**
   - A single human user (`User`) has one global login account (via Supabase Auth) and can belong to multiple Organizations (e.g., an independent consultant working with both an NGO and a university).
   - The user selects their active Organization, and the application loads only the workspaces accessible to them within that Organization.

---

## 2. Subscription Ownership & Lifecycle State Machine

Subscriptions are anchored exclusively to the **Organization**. Workspaces do not possess individual subscriptions; they consume from the Organization's pooled allowance.

### Subscription Lifecycle States

```
           +--------------------+
           |  NEW ORGANIZATION  |
           +--------------------+
                     |
                     v
           +--------------------+
           |     FREE TIER      | <-----------------------+
           +--------------------+                         |
                     |                                    |
                     | Checkout                           |
                     v                                    |
+------------------------------------------+              |
|              TRIALING / ACTIVE           |              |
| - Quotas expanded (Pro / Business)       |              |
| - Renewal scheduled every month/year     |              |
+------------------------------------------+              |
        |                         |                       |
        | Payment Failure         | Cancellation          |
        v                         v                       |
+--------------------+   +---------------------+          |
|      PAST_DUE      |   | CANCEL_AT_PERIOD_END|          |
| - 7-day grace      |   | - Full access until |          |
| - Dunning emails   |   |   period expires    |          |
+--------------------+   +---------------------+          |
        |                         |                       |
        | Unresolved (Day 8+)     | End of Billing Cycle  |
        v                         v                       |
+---------------------------------------------------------+
|                  EXPIRED / DOWNGRADED                   |
| - Reverts to Free limits                                |
| - High-tier features disabled                           |
+---------------------------------------------------------+
```

### Plan Specifications & Limits

| Metric / Feature | Free Tier | Pro Tier ($29/mo) | Business Tier ($149/mo) | Enterprise |
|---|---|---|---|---|
| **Included Seats** | 1 user | 5 users | 20 users | Custom |
| **Additional Seat Cost** | N/A | $8 / seat / mo | $12 / seat / mo | Custom |
| **Workspaces** | 1 | 5 | Unlimited | Unlimited |
| **Storage Quota** | 100 MB | 10 GB | 100 GB | 1 TB+ |
| **Document Limit** | 15 docs | 500 docs | 10,000 docs | Custom |
| **Monthly AI Queries** | 50 queries | 1,500 queries | 10,000 queries | Custom |
| **Available Models** | Gemini Flash / Local | Claude 3.5, GPT-4o, Gemini | Claude Opus 5.5, GPT-6.1, All | Custom Fine-Tuned |
| **OCR Capabilities** | Basic | Full (Amharic, Swahili, English)| High-Throughput Dedicated | Priority OCR |
| **Workspace Roles** | Owner only | Owner, Member | Owner, Admin, Member, Viewer | Custom RBAC |
| **Payment Options** | Free | Stripe, Chapa, Paystack | Stripe, Chapa, Paystack, Wire | Invoiced / PO |

---

## 3. Entitlement & Quota Enforcement Engine

Enforcement occurs server-side in a dedicated module (`backend/entitlements.py`) before any resource allocation or external API consumption.

```
Client Action (Upload / Ask / Invite)
         |
         v
FastAPI Dependency Injection (current_workspace -> parent_organization)
         |
         v
backend.entitlements.verify_action(org_id, action_type, cost)
         |
         +---> Check 1: Subscription Status (active / trialing / grace period)
         |
         +---> Check 2: Quota Availability
         |        - Storage: current_bytes + file_bytes <= plan_storage_bytes
         |        - Documents: current_docs + file_count <= plan_docs
         |        - Members: current_members + 1 <= plan_seats
         |        - AI Queries: cycle_queries + 1 <= plan_monthly_queries
         |
         +---> Pass: Proceed with handler execution
         |
         +---> Fail: Raise HTTPException(status_code=402, detail="Quota exceeded", headers={"X-Upgrade-URL": "/billing"})
```

### Soft Limits vs. Hard Limits
- **Hard Limits (Immediate Block):**
  - Storage Quota: File uploads rejected with descriptive error when bytes exceed plan quota.
  - Member Seats: Invitations blocked until seat count is incremented in billing.
  - Advanced Models: Pro/Business-only models cannot be selected by Free tier organizations.
- **Soft Limits (Graceful Degradation):**
  - AI Monthly Queries: If query limit is reached, organizations receive a warning email. In Pro/Business, administrators can enable "Pay-as-you-go Overages" (billed at token cost + 20% margin) or fall back to unlimited local/canned retrieval answers.

---

## 4. Usage Metering & Real-Time Aggregation

Usage is tracked across two dimensions: **Continuous State Metrics** (storage bytes, document count, active seats) and **Cumulative Event Metrics** (AI queries, input tokens, output tokens, OCR pages processed).

### Metering Architecture

1. **Continuous State Tracking:**
   - Maintained dynamically via transactional database aggregates and verified during file operations:
     ```python
     def get_organization_storage(org_id: str) -> int:
         return sum(store.get_store(ws["id"]).bytes_used() for ws in db.list_org_workspaces(org_id))
     ```
2. **Cumulative Event Logging (`usage` table):**
   - Every AI request records an append-only row into SQLite `usage`:
     - `organization_id`, `workspace_id`, `user_id`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `created_at`.
3. **Monthly Billing Cycle Partitioning:**
   - Reset date is anchored to `subscriptions.current_period_start`.
   - Aggregations query `WHERE organization_id = ? AND created_at >= ?` with composite indexing on `(organization_id, created_at)` for instant sub-millisecond calculation.

---

## 5. Payment Provider Abstraction Layer

AfriSearch AI serves both global institutions and African regional organizations. A provider-agnostic billing adapter layer isolates the application from individual payment gateway nuances.

```
                             +-------------------------------+
                             |   PaymentService Interface    |
                             |   (backend/billing/base.py)   |
                             +-------------------------------+
                                             |
             +-------------------------------+-------------------------------+
             |                               |                               |
             v                               v                               v
+--------------------------+   +---------------------------+   +--------------------------+
|      StripeAdapter       |   |       ChapaAdapter        |   |     PaystackAdapter      |
| - International Cards    |   | - Ethiopia (Telebirr,     |   | - Kenya (M-Pesa, Card)   |
| - Apple / Google Pay     |   |   CBE Birr, Awash)        |   | - Nigeria, Ghana Mobile  |
| - Subscriptions & Portal |   | - Hosted Checkout Link    |   | - Subscriptions API      |
+--------------------------+   +---------------------------+   +--------------------------+
```

### Standard Gateway Methods
```python
class PaymentGateway(ABC):
    @abstractmethod
    def create_customer(self, org: Organization) -> str: ...
    
    @abstractmethod
    def create_checkout_session(self, org: Organization, plan: Plan, return_url: str) -> str: ...
    
    @abstractmethod
    def create_portal_session(self, customer_id: str, return_url: str) -> str: ...
    
    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent: ...
```

---

## 6. Payment Webhook Processing & Idempotency Pipeline

Webhooks are untrusted inbound HTTP POST requests that must be cryptographically authenticated, logged, and processed idempotently to guarantee that a network retry never results in double billing or multiple plan updates.

```
Inbound Webhook POST (/api/billing/webhooks/{provider})
         |
         v
Step 1: Cryptographic Signature Validation
        (Reject with 401 if HMAC signature does not match secret)
         |
         v
Step 2: Idempotency Record Check
        SELECT 1 FROM webhook_events WHERE provider = ? AND event_id = ?
        - If EXISTS: Return HTTP 200 immediately (Already processed)
        - If NOT EXISTS: Insert into webhook_events with status = 'processing'
         |
         v
Step 3: Event Dispatching (Atomic Transaction)
        BEGIN TRANSACTION
          - 'checkout.session.completed': Activate subscription, record payment
          - 'invoice.payment_succeeded': Advance current_period_end, reset dunning
          - 'invoice.payment_failed': Transition to 'past_due', send dunning email
          - 'customer.subscription.deleted': Transition to 'canceled'
        COMMIT
         |
         v
Step 4: Update webhook_events status = 'completed' -> Return HTTP 200
```

---

## 7. Role-Based Access Control (RBAC) Architecture

AfriSearch implements a two-tier RBAC system: **Organization-Level Roles** (governing billing, seats, and workspace creation) and **Workspace-Level Roles** (governing document management and research chats).

### Organization Roles

| Organization Role | Manage Billing & Plan | Invite Org Members | Create Workspaces | Delete Organization |
|---|:---:|:---:|:---:|:---:|
| **Owner** | Yes | Yes | Yes | Yes |
| **Billing Admin** | Yes | No | No | No |
| **Admin** | No | Yes | Yes | No |
| **Member** | No | No | Only if permitted | No |

### Workspace Roles

| Workspace Role | Upload / Replace Docs | Delete / Tag Docs | Ask Questions / Chat | View Shared Chats | Manage Workspace Members |
|---|:---:|:---:|:---:|:---:|:---:|
| **Workspace Owner** | Yes | Yes | Yes | Yes | Yes |
| **Workspace Admin** | Yes | Yes | Yes | Yes | Yes (except Owner) |
| **Workspace Member**| Yes | No (own only) | Yes | Yes | No |
| **Workspace Viewer**| No | No | Yes (Read-only) | Yes | No |

---

## 8. Multi-Tenant Data Isolation Strategy

Data isolation prevents cross-tenant data contamination across database records, physical filesystem uploads, and vector search indices.

### 1. Database Level (Logical Isolation)
- Every query executes with mandatory foreign key scoping:
  ```sql
  SELECT * FROM documents WHERE workspace_id = :ws_id AND organization_id = :org_id;
  ```
- SQLite foreign key enforcement is enabled globally on every connection: `PRAGMA foreign_keys = ON;`.

### 2. File Storage Level (Physical Path Isolation)
- Uploads are saved in strict directory silos:
  `DATA_DIR/workspaces/{workspace_id}/uploads/{hash}_{name}`
- Path traversal defense: `store.py:file_path` verifies that the resolved path is strictly a descendant of the workspace's designated `uploads` folder:
  ```python
  if self.upload_dir.resolve() not in target_path.resolve().parents:
      raise PermissionError("Access denied.")
  ```

### 3. Vector Index Level (Semantic Isolation)
- Chunks and embeddings are stored inside the workspace folder (`DATA_DIR/workspaces/{workspace_id}/embeddings.npy`).
- Semantic retrieval loads only the vectors associated with the target workspace. Cross-workspace similarity calculation is architecturally impossible in this layout.

---

## 9. Phased Database Migration Roadmap: SQLite to PostgreSQL + pgvector

While SQLite with WAL mode is exceptionally fast and reliable for single-node deployments up to hundreds of workspaces, scaling to thousands of concurrent organizations requires horizontal scaling across multiple application nodes.

```
+------------------------------------+       +------------------------------------+
|       STAGE 1: CURRENT ARCH        |       |       STAGE 2: PGVECTOR ARCH       |
| - Relational Data: SQLite WAL      |       | - Relational Data: PostgreSQL 16   |
| - Vectors: Per-workspace NumPy     |  ==>  | - Vectors: pgvector (HNSW Index)   |
| - Files: Local data volume         |       | - Files: S3-Compatible Object Store|
| - Scope: Single Uvicorn Node       |       | - Scope: Multi-container Stateless |
+------------------------------------+       +------------------------------------+
```

### Migration Plan (Zero-Downtime Strategy)

1. **Phase 1: Abstract Data Access Layer (DAL):**
   - Refactor `backend/db.py` queries into a Repository pattern with standard interface abstractions.
2. **Phase 2: PostgreSQL Schema & pgvector Setup:**
   - Create identical relational schema in PostgreSQL.
   - Replace `index.json` and `embeddings.npy` with a unified `chunks` table:
     ```sql
     CREATE TABLE chunks (
         id TEXT PRIMARY KEY,
         workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
         source_id TEXT NOT NULL,
         source_name TEXT NOT NULL,
         page INTEGER,
         page_end INTEGER,
         ocr BOOLEAN DEFAULT FALSE,
         text TEXT NOT NULL,
         embedding vector(384) -- Matches multilingual-e5-small dimensions
     );
     CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
     ```
3. **Phase 3: Object Storage Migration:**
   - Replace local disk uploads with an S3-compatible client (MinIO for dev, AWS S3 / Cloudflare R2 for production).
4. **Phase 4: Data Migration Script:**
   - Execute streaming migration from SQLite `afrisearch.db` and NumPy matrices into PostgreSQL tables with verification checks.

---

## 10. Background Processing & Indexing Scalability

The current in-process single-thread executor (`ThreadPoolExecutor(max_workers=1)`) must evolve to handle heavy concurrent indexing workloads without degrading API response times.

```
Client Upload Request
         |
         v
FastAPI Upload Handler (Saves raw file to S3/Volume & creates Job record 'queued')
         |
         v
Enqueue Task -> Redis Queue (RQ / Celery / ARQ)
         |
         +-----------------------+-----------------------+
         |                       |                       |
         v                       v                       v
Worker 1 (GPU/OCR Node)   Worker 2 (CPU Embedder)   Worker 3 (Document Parser)
- Text extraction         - Sentence Chunking       - Batch Embedding
- Tesseract OCR (Amh/Swa) - Markdown conversion     - Vector Index Insert
         |                       |                       |
         +-----------------------+-----------------------+
                                 |
                                 v
                 Update Job Status: 'done' in Database
                 Send Notification Email if duration > 60s
```

### Scaling Milestones
- **Milestone A (Current):** Single in-process worker. Adequate for pilot (2-5 organizations, sequential uploads).
- **Milestone B (Pilot Growth):** Multi-threaded worker pool (`max_workers=4`) with process-level isolation for Tesseract OCR.
- **Milestone C (Commercial Scale):** Dedicated worker instances running Redis + Celery, enabling independent scaling of API servers and GPU-accelerated embedding workers.
