# 🎓 CampusConnect — Phase-by-Phase Build Plan

> **Origin**: Evolved from [CampusMind](https://github.com/YOUR_USERNAME/CampusMind)  
> **Goal**: A production-grade, multi-tenant AI classroom platform that demonstrates real distributed systems engineering.

---

## Why This Exists (And Why Not Just Use Gemini/NotebookLM)

NotebookLM is a single-user tool. CampusConnect solves a fundamentally different problem: **one teacher uploads material, 200 students get a scoped AI tutor — with real-time updates, background processing, role-based access, and cost-optimized routing.** The engineering challenge isn't the chatbot — it's the system around it.

---

## Architecture Overview

```
                         ┌────────────────────────┐
                         │    Nginx (HTTPS/TLS)    │
                         │   Reverse Proxy + SSL   │
                         └──────────┬─────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
             ┌──────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐
             │  Next.js 16  │ │ FastAPI     │ │  WebSocket  │
             │  Frontend    │ │ REST API    │ │  Hub        │
             │  (React 19)  │ │ + SSE Chat  │ │  (Classroom)│
             └──────────────┘ └─────┬──────┘ └──────┬──────┘
                                    │               │
                         ┌──────────┼───────────────┘
                         │          │
                  ┌──────▼──────┐   │
                  │  LangGraph  │   │
                  │  Agent (6   │   │
                  │  nodes)     │   │
                  └──────┬──────┘   │
                         │          │
          ┌──────────────┼──────────┼──────────────┐
          │              │          │              │
   ┌──────▼──────┐ ┌─────▼────┐ ┌──▼───────┐ ┌───▼────────┐
   │  MongoDB    │ │  Redis   │ │ ChromaDB │ │  Celery    │
   │  Atlas      │ │  Stack   │ │ (Server) │ │  Worker    │
   │  (Primary)  │ │ (Cache + │ │ (Vector  │ │  (Solo     │
   │             │ │  Broker +│ │  Store)  │ │   Pool)    │
   │             │ │  PubSub) │ │          │ │            │
   └─────────────┘ └──────────┘ └──────────┘ └────────────┘
```

---

## Tech Stack

| Layer | Technology | Why This Choice |
|-------|-----------|-----------------|
| **Frontend** | Next.js 16, React 19, Tailwind CSS 4, Framer Motion | Server components, streaming, modern DX |
| **Backend** | FastAPI, Python 3.11+, Pydantic v2 | Async-native, auto OpenAPI docs, type safety |
| **AI Agent** | LangGraph (6-node StateGraph) | Conditional routing, proper state management, not a linear chain |
| **LLM** | Google Gemini (2.5 Flash + 1.5 Pro) | Multimodal (PDF images), embeddings, generous free tier |
| **Vector Store** | ChromaDB (server mode) | Cosine similarity, simple API, Docker-ready |
| **Database** | MongoDB Atlas (M0/M2) | Flexible schema for varied doc types, free tier |
| **Cache + Broker** | Redis Stack | 4 roles: Celery broker, result backend, user cache, WebSocket PubSub |
| **Task Queue** | Celery (solo pool) | Background PDF processing, retry logic, time limits |
| **Reverse Proxy** | Nginx + Let's Encrypt | HTTPS, static file serving, WebSocket upgrade |
| **Deployment** | DigitalOcean Droplet + Docker Compose | Single-machine, cost-effective, full control |

---

## Phase Plan

---

### Phase 0 — Project Foundation

**Goal**: Clean repo structure, environment setup, Docker infrastructure.

**What you build**: Nothing user-facing. Just the skeleton.

#### Files to Create

```
CampusConnect/
├── .github/
│   └── workflows/           # CI placeholder (Phase 6)
├── backend/
│   ├── .env.example          # Template with placeholder values (NEVER real secrets)
│   ├── pyproject.toml        # Python dependencies
│   ├── main.py               # Empty FastAPI app with lifespan
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py         # Pydantic Settings (reads from env)
│   ├── database/
│   │   ├── __init__.py
│   │   ├── mongo.py          # Motor async client singleton
│   │   └── redis.py          # Redis async client singleton
│   └── models/
│       ├── __init__.py
│       └── schemas.py        # Pydantic schemas (empty)
├── frontend/
│   ├── package.json
│   ├── next.config.ts
│   ├── middleware.ts          # Auth guard
│   └── app/
│       ├── layout.tsx
│       ├── globals.css
│       └── page.tsx           # Landing/login redirect
├── docker-compose.yml         # MongoDB + Redis + ChromaDB (server mode)
├── .gitignore                 # Comprehensive (no .env, no node_modules, no __pycache__)
├── .env.example               # Root-level example
├── README.md
└── CAMPUS_CONNECT_BUILD_PLAN.md  # This file
```

#### docker-compose.yml Services (Phase 0)

```yaml
services:
  mongodb:        # MongoDB 7.0 with auth
  redis:          # Redis Stack (cache + broker + pubsub)
  chromadb:       # ChromaDB server mode (NOT embedded)
  mongo-express:  # Admin UI (dev only)
```

#### Key Decisions

- **ChromaDB runs as a Docker service** (`chromadb/chroma` image), not embedded. FastAPI and Celery both connect via HTTP client. This eliminates the file-locking problem.
- **MongoDB Atlas for production**, local Docker for dev. Config reads `MONGO_URI` from env.
- **`.env.example`** with placeholder values. Real `.env` is gitignored. Never commit secrets.

#### Milestone
`docker-compose up -d` starts all infra. `uvicorn main:app` starts an empty FastAPI with `/health` that pings all 3 datastores.

---

### Phase 1 — Auth & User Management

**Goal**: JWT authentication, role hierarchy (superadmin → teacher → student), user CRUD.

#### Files to Create/Modify

```
backend/
├── core/
│   └── security.py            # bcrypt hashing + JWT encode/decode
├── api/
│   ├── __init__.py
│   ├── dependencies.py        # get_current_user (JWT + Redis cache), require_role()
│   └── routers/
│       ├── __init__.py
│       ├── auth.py            # POST /register, POST /login, GET /me, PATCH /me
│       └── superadmin.py      # POST /provision-teacher, GET /users, DELETE /users/:id
├── models/
│   └── schemas.py             # UserCreate, TokenResponse, RoleEnum, etc.
frontend/
├── app/
│   ├── login/page.tsx
│   ├── signup/page.tsx
│   ├── context/auth-context.tsx   # Auth provider with cookie-based token
│   └── lib/api.ts                 # Fetch wrapper with auth headers
```

#### Architecture Decisions

- **Redis user cache**: Authenticated user profile cached for 5 min in Redis (`user_cache:{user_id}`). Avoids MongoDB hit on every API call. Cache invalidated on password/profile change.
- **Superadmin auto-seed**: Created on first startup if not exists. Rejects insecure JWT secrets at boot.
- **Password field excluded from cache**: Store user doc without password hash in Redis to avoid leaking credentials via cache.

#### Milestone
Can register as student, login, get JWT, access protected endpoints. Superadmin can provision teachers.

---

### Phase 2 — Classroom System + Real-Time WebSocket

**Goal**: Create/join classrooms, member management, real-time updates via WebSocket + Redis PubSub.

#### Files to Create/Modify

```
backend/
├── core/
│   └── websocket.py           # ConnectionManager with Redis PubSub listener
├── api/
│   └── routers/
│       ├── classroom.py       # CRUD: create, list, join (by code), detail, delete (cascade)
│       ├── announcements.py   # Create (teacher), list, delete (cascade file+vectors)
│       ├── calendar.py        # Events CRUD with notifications
│       └── notifications.py   # List unread, mark read, clear all
├── main.py                    # Add WebSocket endpoint /ws/classroom/{id}
frontend/
├── app/
│   ├── page.tsx               # Dashboard with classroom cards
│   ├── classroom/[id]/page.tsx
│   ├── hooks/
│   │   ├── useClassrooms.ts
│   │   ├── useClassroomSocket.ts  # WebSocket hook with heartbeat
│   │   └── useAnnouncements.ts
│   └── components/
│       ├── ClassroomCard.tsx
│       └── AnnouncementFeed.tsx
```

#### Architecture Decisions

- **WebSocket Hub**: Classroom-scoped. Each classroom has its own connection pool. JWT auth via query param on WS upgrade.
- **Redis PubSub bridge**: Celery worker → Redis publish → FastAPI PubSub listener → WebSocket broadcast. This lets background tasks notify connected clients without direct WebSocket access.
- **PubSub reconnection**: Listener wraps in `while True` with exponential backoff on failure. Never silently dies.
- **Join codes**: 6-char alphanumeric, collision-checked, unique indexed.
- **Cascade deletes**: Deleting a classroom removes: files (disk + vectors), chat sessions + history, announcements, notifications. All in one endpoint.

#### Milestone
Teacher creates classroom → students join via code → announcements posted → real-time WebSocket push to all connected members.

---

### Phase 3 — File Upload + Celery Ingestion Pipeline

**Goal**: File upload with SHA-256 dedup, 3-tier background extraction, vector storage.

#### Files to Create/Modify

```
backend/
├── core/
│   ├── celery_app.py          # Celery config (Redis broker, solo pool, retry, time limits)
│   └── llm_router.py         # 3 key pools (ROUTER/CHAT/INGESTION) + model chains + fallback
├── database/
│   └── chroma.py              # ChromaDB HttpClient (server mode, NOT PersistentClient)
├── api/
│   ├── services/
│   │   └── ingestion.py       # 3-tier: Gemini File API → Docling → PyMuPDF
│   └── routers/
│       └── upload.py          # POST /upload, GET /files, GET /files/:id, POST /files/:id/retry
├── storage/
│   ├── temp/                  # Temp upload dir (cleaned by Celery Beat)
│   └── uploads/
│       ├── pdfs/
│       └── images/
```

#### 3-Tier Extraction Pipeline

```
PDF Upload
    │
    ▼
┌─────────────────────────────────────────┐
│ Tier 1: Gemini File API (multimodal)     │  ← Best: tables, diagrams, equations
│   ↓ fails?                               │
│ Tier 2: Docling (local ML)               │  ← Good: structured text, basic tables
│   ↓ fails?                               │
│ Tier 3: PyMuPDF (text-only)              │  ← Fallback: plain text, no understanding
└─────────────────────────────────────────┘
    │
    ▼
Chunk (800 chars, 100 overlap) → Embed (gemini-embedding-001) → Store in ChromaDB
    │
    ▼
Update MongoDB status → Notify via Redis PubSub → WebSocket broadcast
```

#### Architecture Decisions

- **Celery connection pooling**: Initialize MongoDB + ChromaDB on `worker_init` signal, not per-task. Close on `worker_shutdown`.
- **Idempotent tasks**: SHA-256 dedup means re-uploading the same file is a no-op. Re-trigger on failure.
- **`task_acks_late=True`**: Task only acknowledged AFTER completion. If worker dies mid-task, it's requeued automatically.
- **Extraction method tracked**: MongoDB stores which tier extracted the file. Students warned if low-quality fallback was used.

#### Milestone
Teacher uploads PDF → Celery processes in background → vectors stored → student gets WebSocket notification "file ready" → can now ask questions about it.

---

### Phase 4 — LangGraph AI Agent + SSE Chat

**Goal**: 6-node agentic pipeline with intent routing, scoped RAG, web search, and per-token SSE streaming.

#### Files to Create/Modify

```
backend/
├── api/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── state.py           # TypedDict state: AgentState with all fields documented
│   │   ├── nodes.py           # 6 node implementations
│   │   └── graph.py           # StateGraph assembly + conditional edges
│   └── routers/
│       └── chat.py            # SSE streaming endpoint, session CRUD, Redis cache
frontend/
├── app/
│   ├── classroom/[id]/
│   │   └── chat/page.tsx      # Chat UI with SSE streaming
│   ├── hooks/
│   │   └── useChat.ts         # SSE parser, token accumulation, source display
│   └── components/
│       ├── ChatMessage.tsx     # Markdown + KaTeX + code block rendering
│       └── SourceCitation.tsx  # File name + page number display
```

#### LangGraph Flow

```
START → entry_node → router_node ──┬── OUT_OF_SCOPE → fast_reject → END
                                   ├── CONVERSATIONAL → END (synthesis from SSE)
                                   └── RAG/WEB/DEEP → embed_node ──┬── retriever → END
                                                                    └── web_search → END

After graph END → synthesis_node_stream (async generator, per-token SSE)
```

#### Architecture Decisions

- **Router node uses cheapest model**: `gemini-2.5-flash-lite` for classification. ~60% of queries never hit the expensive model.
- **Synthesis is NOT a graph node**: LangGraph doesn't support per-token streaming inside nodes. Synthesis runs as an async generator from the SSE endpoint after the graph populates state. This is the correct pattern.
- **Relevance threshold (0.35)**: Chunks below this cosine similarity are silently dropped. Only high-confidence chunks reach synthesis. Prevents hallucination from irrelevant context.
- **Redis response cache**: SHA-256 of `(classroom_id + file_id + query)` → cached response for 24 hours. Only RAG/CONVERSATIONAL cached, not web search (stale quickly).

#### Milestone
Student asks a question → LangGraph classifies intent → retrieves relevant chunks → streams answer token-by-token with source citations → response cached.

---

### Phase 5 — Semantic Cache + Bug Fixes + Polish

**Goal**: The "production quality" phase. Semantic cache, all bug fixes, proper error handling.

#### Semantic Cache Implementation

```
Incoming query
    │
    ▼
Embed query (reuse embed_node logic)
    │
    ▼
Search cache index (last 500 query embeddings per classroom)
    │
    ▼
cosine_similarity > 0.93? ── YES → Return cached response (fast path)
    │
    NO
    │
    ▼
Run full LangGraph agent → Store response + embedding in cache
```

#### Bug Fixes (from audit)

| Bug | Fix |
|-----|-----|
| `time.sleep()` blocking event loop | Replace with `await asyncio.sleep()` in async contexts |
| Celery creates new DB connections per task | Use `worker_init` / `worker_shutdown` signals |
| `datetime.utcnow()` in calendar | Replace with `datetime.now(timezone.utc)` |
| N+1 queries in calendar events | Batch-fetch creators and classrooms in 2 queries |
| WebSocket PubSub no reconnection | Wrap listener in `while True` with backoff |
| `invalidate_user_cache` uses deprecated API | Use `asyncio.get_running_loop()` |
| Password hash cached in Redis | Exclude `password` field before caching user doc |
| Static files served by FastAPI | Move to Nginx in Phase 6 |

#### Additional Polish

- Structured JSON logging with configurable log levels
- Consistent error response format across all endpoints
- Rate limiting on login endpoint (slowapi)
- Input validation tightened on all endpoints

#### Milestone
All known bugs fixed. Semantic cache reduces redundant API calls. Error handling is consistent. Logging is structured.

---

### Phase 6 — Dockerize + Deploy to DigitalOcean

**Goal**: Full Docker Compose stack deployed on a single DigitalOcean droplet with HTTPS.

#### Files to Create

```
CampusConnect/
├── backend/
│   └── Dockerfile             # Python 3.11-slim, uv install, gunicorn entrypoint
├── frontend/
│   └── Dockerfile             # Node 20-alpine, next build, standalone output
├── nginx/
│   ├── nginx.conf             # Reverse proxy config
│   └── Dockerfile             # nginx:alpine + config copy
├── docker-compose.yml         # Full stack (8 services)
├── docker-compose.dev.yml     # Dev overrides (hot reload, no nginx)
└── .github/
    └── workflows/
        └── deploy.yml         # SSH deploy on push to main
```

#### Production docker-compose.yml

```yaml
services:
  # ── Infrastructure ──
  redis:
    image: redis/redis-stack-server:latest
    volumes: [redis_data:/data]
    command: redis-server --appendonly yes  # AOF persistence

  chromadb:
    image: chromadb/chroma:latest
    volumes: [chroma_data:/chroma/chroma]

  # ── Application ──
  backend:
    build: ./backend
    command: gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
    env_file: .env
    depends_on: [redis, chromadb]
    volumes: [upload_storage:/app/storage]

  celery-worker:
    build: ./backend
    command: celery -A core.celery_app worker --loglevel=info -P solo
    env_file: .env
    depends_on: [redis, chromadb]
    volumes: [upload_storage:/app/storage]

  flower:
    build: ./backend
    command: celery -A core.celery_app flower --port=5555
    depends_on: [redis]

  frontend:
    build: ./frontend
    environment:
      NEXT_PUBLIC_API_URL: https://YOUR_DOMAIN

  # ── Edge ──
  nginx:
    build: ./nginx
    ports: ["80:80", "443:443"]
    volumes:
      - letsencrypt:/etc/letsencrypt
      - upload_storage:/static
    depends_on: [backend, frontend]
```

#### Nginx Routing

```
https://campusconnect.your-domain.com
  ├── /                → frontend:3000
  ├── /api/*           → backend:8000
  ├── /ws/*            → backend:8000 (WebSocket upgrade)
  ├── /static/*        → Direct file serving from volume
  └── /flower/         → flower:5555 (password-protected)
```

#### DigitalOcean Setup

```bash
# 1. Create Droplet ($12/mo, 2GB RAM, Ubuntu 24.04)
# 2. SSH in, install Docker + Docker Compose
# 3. Point domain DNS A record → Droplet IP
# 4. Clone repo, create .env, get SSL cert
# 5. docker compose up -d --build
# 6. Verify: curl https://campusconnect.your-domain.com/api/health
```

#### MongoDB Atlas Setup

```
1. Create free M0 cluster (or M2 with $50 credit)
2. Create database user + whitelist Droplet IP
3. Get connection string → paste in .env as MONGO_URI
```

#### Milestone
`https://campusconnect.your-domain.com` is live with HTTPS, all services running, health check green.

---

### Phase 7 — Demo Preparation & Documentation

**Goal**: Make it interview-ready. README, architecture docs, demo seed script.

#### Files to Create/Update

```
CampusConnect/
├── README.md                  # Professional README with screenshots, arch diagram, setup guide
├── docs/
│   ├── ARCHITECTURE.md        # System design document with diagrams
│   ├── API_REFERENCE.md       # Key endpoints (or link to /docs)
│   └── DESIGN_DECISIONS.md    # Why each technology was chosen
└── scripts/
    └── seed_demo.py           # Populate demo data (classroom, files, chat history)
```

#### Interview Prep Checklist

- [ ] Live URL works with HTTPS
- [ ] Can demo full flow: register → login → create classroom → upload PDF → chat with AI
- [ ] Can show Flower monitoring dashboard
- [ ] Can explain every architectural decision
- [ ] Can show `/api/docs` (auto-generated OpenAPI)
- [ ] Can describe roadmap (YouTube chunking, confusion detection)

---

## Summary Timeline

| Phase | What | Est. Time |
|-------|------|-----------|
| 0 | Foundation + Docker infra | 2 hours |
| 1 | Auth + User Management | 4 hours |
| 2 | Classrooms + WebSocket | 6 hours |
| 3 | Upload + Celery Ingestion | 6 hours |
| 4 | LangGraph Agent + SSE Chat | 8 hours |
| 5 | Semantic Cache + Bug Fixes | 4 hours |
| 6 | Dockerize + Deploy | 3 hours |
| 7 | Demo Prep + Docs | 2 hours |
| **Total** | | **~35 hours** |

---

## Key Interview Talking Points

| Decision | Why | Alternative Considered |
|----------|-----|----------------------|
| **Redis as broker (not RabbitMQ)** | Serves 4 roles in one service. At campus scale, task loss = reprocess, not corruption. | RabbitMQ: better durability, unnecessary complexity. |
| **LangGraph (not LangChain)** | Conditional branching. Can't skip embedding for conversational queries with a linear chain. | Raw async functions: loses graph visualization. |
| **Gemini (not OpenAI/DeepSeek)** | Multimodal (PDF images), embeddings, free tier. One provider, not two. | DeepSeek: cheaper text, can't handle images. |
| **ChromaDB server mode (not embedded)** | Eliminates file locking between FastAPI and Celery. Same API, zero migration. | Qdrant: better long-term, unnecessary for demo. |
| **Synthesis outside LangGraph** | Framework limitation — no per-token streaming inside nodes. Async generator is correct pattern. | Buffered response: destroys streaming UX. |
| **3-tier extraction** | Gemini can fail. Docling handles structured PDFs. PyMuPDF ensures we never fail silently. | Single-tier: fragile, one outage = all uploads fail. |
| **Semantic cache** | "What is Newton's second law?" and "Explain F=ma" are identical queries with different SHA-256 hashes. | Exact-match only: misses ~30-40% of cache hits. |

---

> **Repo**: This plan is for `github.com/YOUR_USERNAME/CampusConnect`.  
> The original CampusMind repo is preserved as development history.
