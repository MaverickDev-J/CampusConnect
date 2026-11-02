# CampusConnect

An AI learning platform with classroom-scoped document chat and faculty workflows that require human approval before posting.

**[Open the live application](https://yjoy1572--campusconnect-postgres-frontend-web.us-east.modal.run)**

Faculty upload course PDFs and manage classrooms. Enrolled students ask questions, receive streamed answers, and inspect cited document pages. Faculty can prepare a sourced revision-session announcement and calendar event, review and approve the draft, and inspect its execution trace.

## Current architecture

| Layer | Implementation |
| --- | --- |
| Frontend | Next.js, student/faculty views, source previews, Quality & Runs dashboard |
| API | FastAPI, REST, SSE chat streaming, authenticated WebSockets |
| Chat workflow | Seven-node LangGraph with exact-cache lookup and conditional conversational/retrieval/web/out-of-scope routing |
| Retrieval | Gemini Embedding 2, 1536-dimensional pgvector search, weighted PostgreSQL full-text search, Reciprocal Rank Fusion |
| Text models | Groq `openai/gpt-oss-120b` for routing, generation, bounded reranking and faculty drafts |
| Tools and actions | Six authenticated MCP tools; separate durable LangGraph review/execute workflow |
| Persistence | Neon PostgreSQL, row-level security, revisioned chunks, payload-bound approvals, transactional actions and outbox |
| Background processing | Leased ingestion/delivery/cleanup jobs, bounded Modal workers, hourly rescue |
| Deployment | Modal API/frontend containers and persistent upload volume; managed PostgreSQL in Neon |
| Live updates | Redis Pub/Sub and classroom-authorized WebSockets |

Course answers use supplied evidence and acknowledge missing information. Exact-answer reuse checks the user, classroom, history, document revision, corpus version, and answer policy. Semantic reuse is disabled. Shared provider budgets preserve answer capacity; retrieval and reranking fallbacks are recorded explicitly.

Faculty approval is bound to the draft version and payload hash. Repeated execution returns the persisted result. Notification delivery can repeat; PostgreSQL protects the underlying domain actions.

## Run and inspect

The active API entry point is `backend/postgres_main.py`. Configure a restricted runtime `DATABASE_URL`, Redis, a strong JWT secret, Groq credentials, and Gemini embedding credentials in the ignored environment file. Provision schemas and API/worker roles using [OPERATIONS.md](OPERATIONS.md).

```sh
cd backend
uv sync --frozen
uv run uvicorn postgres_main:app --reload --port 8000
```

```sh
cd frontend
npm ci
npm run dev
```

Local PostgreSQL is available through `docker compose -f compose.postgres.yml up -d --wait`. Hosted ingestion and delivery use `backend/modal_staging.py`. The older MongoDB/Chroma/Celery entry points and compose files remain legacy code, separate from the deployed PostgreSQL application.

## Verification and evaluation

Tests cover restricted-role API/database access, MCP authorization, ingestion/revision/cache behaviour, approval/retry recovery, and correlated workflow/background tracing. Operational verification includes 10,000-chunk local retrieval, five concurrent scoped principals, isolated Modal startup probes, and a disposable Neon point-in-time recovery rehearsal.

The private evaluation contains 60 cases. Fifty retrieval comparisons and ten hosted authorization checks are recorded; source labels require faculty review. Provisional results on the networking PDF favour dense retrieval, so no hybrid accuracy improvement is claimed. Budget fallbacks and sampled answer regressions are reported separately from retrieval scores.

- [Interview walkthrough and measured claim limits](INTERVIEW_DEMO.md)
- [Deployment, tests, quotas, retention and recovery](OPERATIONS.md)

Private source excerpts, credentials, generated-answer reports, and the local implementation plan are excluded from Git.
