# PostgreSQL development

From the repository root:

```powershell
docker compose -f compose.postgres.yml up -d --wait
cd backend
$env:DATABASE_URL='postgresql+psycopg://campusconnect:campusconnect-local@127.0.0.1:5433/campusconnect'
uv run alembic upgrade head
$env:TEST_DATABASE_URL='postgresql://campusconnect:campusconnect-local@127.0.0.1:5433/campusconnect'
uv run python -m unittest discover -s tests -v
```

The Compose password is for loopback-only local development. Use a secret and TLS
for a hosted database. The application still uses the legacy store while route
migration is in progress; these migrations do not switch production traffic.

Migration 001 creates the first application tables, vector storage, and lexical
index. Migration 002 adds classroom read policies. Migration 003 adds account and
classroom write policies and narrow login, registration, and join functions.
Migration 005 adds announcements, calendar actions, recipient-scoped notifications,
idempotent operations, and an outbox for committed update events. The staging API
now mounts those REST routes as well.
Provision a separate non-owner login role and apply `runtime_grants.sql` with psql's
`runtime_role` variable set to that role. Never run the API as the migration owner.
Runtime credentials cannot select the password-hash column or update user roles.
Login's restricted function retrieves one account's credential for verification.
Profile and classroom access use current transaction-scoped identity.

Set DATABASE_URL to that runtime login, then run:

```powershell
uv run python postgres_main.py
```

The staging API listens on loopback port 8001 and serves the existing auth/profile
and classroom routes, file upload/list/detail/download/retry, and chat session/
history/SSE routes, plus `/health`. It rejects owner/bypass-RLS connections at
startup. Production `main:app` still uses the legacy store; the staging entrypoint
is for migration verification and will gain the remaining routes before cutover.
Keep it local until rate limiting, hosted CORS/origin configuration, remaining routes,
and deployment checks are complete. Migration 006 enables safe file/classroom
deletion and the PostgreSQL WebSocket gateway.
Local frontend ports 3000/3001 are allowed by staging CORS. Set the frontend's
NEXT_PUBLIC_API_URL to `http://localhost:8001` when verifying the migrated routes.

Migration 004 adds scoped file writes, a durable ingestion queue, and owner-scoped
chat policies. Uploaded files and job records are registered together in a database
transaction. Duplicate content is deduplicated within a classroom. Downloads always
check current identity and membership; the staging app has no public static mount.

Run an ingestion worker in a separate process with a separate non-owner login.
Apply `runtime_grants.sql` and then `worker_grants.sql` to that worker role. Set its
DATABASE_URL, the same STORAGE_DIR as the API, and existing Gemini credentials:

```powershell
uv run python ingestion_worker.py
```

The API role cannot claim jobs. Workers claim jobs using SKIP LOCKED and a lease,
persist extracted chunks before embedding, and save each successful vector. A
restart can reclaim an expired lease and reuse those vectors. Failed work retries
after 30 seconds, at most three attempts; the authorized retry endpoint can reset
a failed job. Revision 1 is for new Embedding 2 documents only; legacy vectors need
a separately versioned import/re-embedding path, which is not a cutover procedure
yet. Native PDF extraction preserves real page numbers; fallback extraction uses
null page provenance instead of inventing page references. Chunking currently uses
300-word windows with 40-word overlap, not a tokenizer-based token guarantee.

Chat runs a PostgreSQL LangGraph with the shared router, Embedding 2, lexical/vector
RRF, and optional API reranking. Query embedding failure falls back to lexical
retrieval. Reranking failure falls back to RRF. No legacy answer caches are reused
until safe corpus/permission-versioned cache keys are integrated. Chat turns have
an exclusive expiring lease, and user/assistant history is committed atomically
after generation succeeds. Provider failures return the existing SSE error/done
contract without persisting incomplete answers. Source revisions are rechecked
before saving a completed turn. The API provider quota budget, full source-quality
evaluation and final hosted worker topology remain
release gates. File-list polling keeps pending upload status visible locally.

Campus actions create their notification records in the same database transaction.
An optional `Idempotency-Key` header makes repeated requests return the original
result; reusing that key for different content returns 409. The shared
`CampusActions.revision_session` service commits an announcement, event, recipient
notifications, and outbox records atomically. It is not exposed as an unapproved
MCP write tool; the faculty workflow now enforces approval before using that
transaction primitive.

Global calendar events require a superadmin. Classroom members can read scoped
events and announcements; notifications are visible only to their recipient while
that recipient retains classroom access. Deleting an announcement preserves its
underlying document because files can be shared by multiple posts and sessions.
`DELETE /api/files/{file_id}` now queues explicit document cleanup (202). In the
same transaction, the source becomes unavailable to list/download/retrieval,
ingestion jobs are cancelled, and chunk/revision rows are removed. Historical chat
transcripts are retained; their prior generated content is not source retrieval.
Classroom deletion queues all document paths before cascading database records.
The cleanup queue deliberately survives removal of the classroom and uploader.

The outbox worker also processes physical cleanup. It resolves each path against
the configured STORAGE_DIR, rejects external/symlink paths, checks active file
references, and unlinks only individual queued files. Missing files count as
success after a crash between unlink and acknowledgement. Failed cleanup retries
after 30 seconds with at most five attempts; inspect exhausted rows before requeue.
Run it with the same mounted storage root as the API/ingestion worker and reapply
worker grants after migration. No recursive directory deletion is performed.

Run event delivery separately using a restricted worker login with
`runtime_grants.sql` plus `worker_grants.sql`, and DATABASE_URL / REDIS_URL:

```powershell
uv run python outbox_worker.py
```

The dispatcher leases events, publishes to the existing `classroom_updates` Redis
channel, and records success only after publish succeeds. Failed delivery retries
after 30 seconds, with at most five attempts. Operators can inspect undelivered
outbox rows and deliberately requeue exhausted work. Publish is at least once;
clients should deduplicate event IDs and refresh authoritative REST state after
reconnecting. Notification records remain durable even when no subscriber is
connected.

The PostgreSQL gateway now serves `/ws/classroom/{classroom_id}?token=...` using
the existing handshake/ping/pong contract. It subscribes before acknowledging the
connection, checks token expiry and live PostgreSQL membership at connection,
heartbeats, every relevant update, and at least every 15 seconds while idle.
Revoked connections close with 4003; Redis outages close with 1013 so the existing
client backoff reconnects. A `global_events` subscription receives only global or
currently authorized classroom calendar updates. Local browser origins 3000/3001
are allowed; hosted origins must be configured before deployment. Set the local
frontend NEXT_PUBLIC_WS_URL to `ws://localhost:8001` when checking staging.

To include the actual local Redis-to-WebSocket integration in the backend suite,
set TEST_REDIS_URL to `redis://127.0.0.1:6380/15`; otherwise that test is explicitly
skipped. The other gateway tests use a controlled event transport plus real
PostgreSQL membership checks.

Migration 007 adds faculty drafts and PostgreSQL LangGraph checkpoints. Reapply
`runtime_grants.sql` after upgrading. Checkpoint tables use owner/classroom RLS;
the API never runs checkpointer setup or owns those tables. Draft preparation
retrieves evidence through authenticated MCP, calls Gemini once with a bounded
structured response, then persists a draft and pauses at human review. A failed
provider request does not create campus actions. Drafts expire after 24 hours.

The staging API mounts stateless JSON Streamable HTTP MCP at `/mcp/`. Obtain a
ten-minute MCP credential from `POST /api/mcp/token` using an API access token.
MCP tokens validate issuer, audience, expiry and scope, and cannot access the
human review API. Roles and resource permissions come from current PostgreSQL
records. This is a first-party credential exchange, not generic remote OAuth
onboarding. Do not put either token in URLs, graph state, or source control.

The curated tools are `list_courses`, `search_documents`, `get_document`,
`prepare_revision_session`, `get_workflow_status`, and
`execute_approved_revision_session`. There is no approval tool. Use the independent
client from the backend directory with CAMPUS_API_TOKEN set in your environment:

```powershell
uv run python -m scripts.mcp_client list_courses
```

Enable the local frontend review panel with NEXT_PUBLIC_FACULTY_WORKFLOWS=true
and the API/WS URLs above before starting or building Next.js. Teachers see the
panel inside a classroom; server permissions restrict drafts to the classroom's
faculty owner or a superadmin. The panel restores saved drafts, shows source
excerpts/pages, supports editing and rejection, and separates approval from
posting. An edit increments the revision and clears approval. Approve/reject
requests must supply the current version and payload hash. Expired drafts,
changed source revisions, lost permissions, and past session dates block writes.

Execution locks the owned workflow row. Domain actions, notifications, outbox
records, completion state and graph checkpoints share one database transaction
and connection. Checkpoint pipelines are disabled and checkpoint/node SQL is
serialized on that connection. A failure rolls everything back; retries resume
the saved interrupt and use a deterministic operation key. Completed retries
return the same IDs. Notification delivery remains at least once via the outbox;
the workflow does not claim exactly-once external delivery. Local Edge browser
smoke checks use controlled API responses; backend integration tests use real
PostgreSQL and MCP with controlled generation. Hosting, live Gemini draft quality,
hosted browser verification, and the run timeline remain release gates.

Integration tests require an explicitly selected disposable database and a test
owner that can create temporary roles. SQL fixtures are rolled back; API fixtures
and restricted test roles are explicitly cleaned up. Do not point
TEST_DATABASE_URL at production. Ordinary tests run without this variable and
report database tests as skipped.

On Windows, Psycopg async connections require a selector event loop. The async
integration test and `python postgres_main.py` entrypoint configure that policy.
Linux containers on Modal do not require this override.

PostgreSQL runs in Docker for local development. On Modal the ASGI application
will connect to a persistent PostgreSQL service through DATABASE_URL; running the
database inside the web container is not part of this deployment.

Migration 008 adds shared Gemini admission control. Reapply both runtime and
worker grants after upgrading. All PostgreSQL API/worker processes must use the
same GEMINI_BUDGET_PROJECT label and database. The default label is
`campusconnect-default`; it aggregates every configured key pool conservatively.
It is not automatically discovered from Google credentials. Provision matching
owner-managed policies before using another label. The legacy production
entrypoint does not use these controls until cutover.

Default application caps for light demo use:

| Model | Requests/minute | Reserved input units/minute | Requests/Pacific day | Concurrent calls |
| --- | ---: | ---: | ---: | ---: |
| Gemini 3.8 Flash | 4 | 32,000 | 40 | 2 |
| Gemini Embedding 2 | 10 | 16,000 | 200 | 2 |

Flash reserves 1 request/minute, 8,000 input units/minute, 5 requests/day and one
concurrency slot for answering. Embeddings reserve 2 requests/minute, 4,000 input
units/minute, 20 requests/day and one slot for interactive query embeddings.
Optional routing/reranking/drafts and background work cannot consume that
headroom. An admitted answer is still subject to the total limits; the reserve
does not promise availability when concurrent answers consume the cap.

These are app limits, not verified Google free-tier entitlements or a billing
ceiling. They cannot account for requests made by other applications. Google's
actual project/model quotas may be lower. Request/token windows are rolling 60
seconds; daily counts follow Google's midnight Pacific reset. Reservations remain
charged after errors, cancellation and process death. Concurrency leases expire
after 180 seconds; bounded provider operations finish or time out before that.
Restarting a process does not reset counters.

Text input uses a conservative UTF-8-size reservation including serialized config
and framing allowance, not a claimed exact tokenizer count. The ledger keeps the
larger of reserved and reported input usage for admission. Observed input, output,
and thinking tokens are recorded separately when the SDK supplies them; unknown
usage remains null. Media generation uses a provider token-count request first,
which also consumes an app request allowance. Output budgets are bounded per
workload. No prompt text, API keys, user IDs or document paths enter this ledger.

SDK inference retries are disabled on these paths. HTTP 429 and transient service
errors set a shared model cooldown, honoring Retry-After when supplied. The
PostgreSQL router/extraction paths make one attempt through the existing helper;
they do not rotate to another key or model to bypass this budget. Optional
reranking falls back to RRF, query-embedding failure falls back to lexical search,
and unavailable answer/draft capacity returns a retryable response. Admission
fails closed if the budget database is unavailable or a policy is missing.
Accounting failure after a provider call never repeats that call; the existing
reservation remains charged and its lease bounds the occupied slot.

Ingestion defers quota-blocked jobs with a retry delay and jitter, retaining
completed embeddings without using failure attempts. Provider 429s also defer
the job. Other provider failures retain the existing bounded failure/retry path.
No external Gemini request is held inside a database transaction.

Inspect or adjust caps using migration-owner DATABASE_URL from the backend
directory (the API role cannot read or change policies directly):

```powershell
uv run python -m scripts.ai_budget --show
uv run python -m scripts.ai_budget --model gemini-3.8-flash --rpm 3
```

Lower associated reserves when lowering totals below them. Do not reset usage
records to bypass provider limits. Archive/prune old ledger records as scheduled
maintenance; preserve the current Pacific day and active leases. No paid Batch
API, automatic billing upgrade, or local inference server is introduced.
