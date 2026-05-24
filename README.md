# 🎓 CampusConnect

**AI-Powered Campus Learning Platform** — A multi-tenant classroom system where teachers upload course materials and students get a scoped AI tutor with real-time updates, background processing, and cost-optimized LLM routing.

> **Why not just use ChatGPT / NotebookLM?**
> Those are single-user tools. CampusConnect is a distributed system: one teacher uploads material, and 200 students instantly get a classroom-scoped AI tutor — with WebSocket notifications, background PDF processing, and intent-aware routing that prevents unnecessary LLM calls.

---

## Architecture

```
Client → Nginx (Reverse Proxy + HTTPS)
  ├── /api/*     → FastAPI Backend (Gunicorn, 2 workers)
  ├── /ws/*      → WebSocket Hub (Classroom-scoped, Redis PubSub)
  ├── /static/*  → Direct file serving (Nginx, not Python)
  ├── /flower/*  → Celery Monitoring Dashboard
  └── /*         → Next.js Frontend (React 19)

Backend Services:
  ├── LangGraph Agent (6-node StateGraph with conditional routing)
  ├── Celery Worker (3-tier PDF extraction: Gemini → Docling → PyMuPDF)
  ├── Semantic Cache (Vector similarity, not just exact-match)
  └── Gemini Key Rotation (3 isolated pools: Router, Chat, Ingestion)

Data Layer:
  ├── MongoDB Atlas (Users, classrooms, chat history, files)
  ├── Redis Stack (Cache + Celery broker + PubSub + result backend)
  └── ChromaDB Server (Vector store for RAG embeddings)
```

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Next.js 16, React 19, Tailwind 4 | Server components, SSE streaming |
| Backend | FastAPI, Python 3.11+ | Async-native, auto OpenAPI docs |
| AI Agent | LangGraph (6-node StateGraph) | Conditional routing, not linear chains |
| LLM | Google Gemini (Flash + Pro) | Multimodal, embeddings, generous free tier |
| Vector DB | ChromaDB (server mode) | Cosine similarity search |
| Database | MongoDB (Atlas) | Flexible schema, free tier |
| Cache/Broker | Redis Stack | 4 roles in one service |
| Task Queue | Celery (solo pool) | Background PDF processing with retry |
| Reverse Proxy | Nginx | HTTPS, static files, WebSocket upgrade |

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Redis over RabbitMQ** | Redis serves 4 roles (broker, cache, PubSub, results). At campus scale, task loss = file reprocessed, not data corrupted. |
| **LangGraph over LangChain** | Conditional branching lets us skip embedding for conversational queries. Linear chains can't do this. |
| **Synthesis outside the graph** | LangGraph doesn't support per-token streaming inside nodes. Async generator from SSE layer is the correct pattern. |
| **3-tier extraction** | Gemini API can fail (rate limits). Docling handles structured PDFs. PyMuPDF as last resort ensures we never fail silently. |
| **Semantic cache** | "What is F=ma?" and "Explain Newton's 2nd law" are the same question with different SHA-256 hashes. Vector similarity catches these. |
| **ChromaDB server mode** | Embedded mode causes file-locking between FastAPI and Celery. Server mode eliminates this. |

## Quick Start (Development)

```bash
# 1. Start infrastructure
docker-compose up -d    # MongoDB + Redis + ChromaDB

# 2. Backend
cd backend
cp .env.example .env    # Fill in your Gemini API key + JWT secret
uv sync                 # Install Python deps
uvicorn main:app --reload --port 8000

# 3. Celery Worker (separate terminal)
cd backend
celery -A core.celery_app worker --loglevel=info -P solo

# 4. Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## Production Deployment

```bash
# 1. Set up MongoDB Atlas (free M0 cluster)
# 2. Create .env in backend/ with Atlas connection string
# 3. Deploy
docker compose -f docker-compose.prod.yml up -d --build

# 4. Verify
curl http://your-server-ip/health
```

See [CAMPUS_CONNECT_BUILD_PLAN.md](./CAMPUS_CONNECT_BUILD_PLAN.md) for the full architectural design document.

## API Documentation

Once running, visit `/docs` for auto-generated OpenAPI documentation.

## Monitoring

- **Flower Dashboard**: `/flower/` — Celery task monitoring
- **Health Check**: `/health` — Verifies MongoDB, Redis, ChromaDB status
- **Mongo Express**: `:8081` — Database admin UI (dev only)

## License

MIT
