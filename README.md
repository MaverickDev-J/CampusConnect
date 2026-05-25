# 🎓 CampusConnect

### AI-Powered Multi-Tenant Campus Learning Platform

[![Live Demo](https://img.shields.io/badge/%F0%9F%9A%80_Live_Demo-Click_Here-blue?style=for-the-badge)](http://165.22.220.229)

CampusConnect is a distributed, classroom-scoped AI tutoring system. When teachers upload course materials, students instantly get access to a scoped AI tutor with real-time updates, background processing, and cost-optimized LLM routing.

---

## 🛠️ System Architecture & Design

```
Client → Nginx (Reverse Proxy & Static Files)
  ├── /api/*     → FastAPI Backend (Gunicorn, async-native)
  ├── /ws/*      → WebSocket Hub (Classroom-scoped, Redis PubSub)
  ├── /flower/*  → Celery Monitoring Dashboard
  └── /*         → Next.js Frontend (React 19 Server Components)
```

### 🧠 Key System Design Concepts

*   **Multi-Role Redis Stack:** Serves simultaneously as Celery broker, Celery backend, WebSocket PubSub hub, and fast memory cache to minimize infrastructure overhead.
*   **LangGraph StateGraph Agent:** Operates a 6-node state-machine with conditional routing to bypass costly vector database embeddings for simple conversational queries.
*   **3-Tier PDF Ingestion Queue:** An asynchronous Celery pipeline that processes PDFs via Gemini, falling back to Docling and PyMuPDF to ensure zero-failure ingestion under rate limits.
*   **Semantic Cache:** Implements vector-similarity caching rather than exact SHA-256 string matching, allowing questions with similar semantic intent to hit the cache instantly.
*   **Gemini Key Rotation:** Optimizes API limits by rotating keys across 3 isolated pools (Routing, Chat, and Ingestion).
*   **ChromaDB Server Mode:** Decoupled vector store service to eliminate SQLite database-locking issues between FastAPI threads and Celery processes.
*   **Nginx Edge Routing:** Offloads TLS termination and static media file serving directly from Python, upgrading client connections to WebSockets dynamically.

---

## 🚀 Quick Start (Development)

### 1. Run Infrastructure
```bash
docker compose up -d  # Starts MongoDB + Redis + ChromaDB
```

### 2. Backend & Celery Worker
```bash
cd backend
cp .env.example .env    # Configure Gemini API keys & DB URLs
uv sync                 # Install Python dependencies
uvicorn main:app --reload --port 8000

# Start Celery (in separate terminal)
celery -A core.celery_app worker --loglevel=info -P solo
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev             # Next.js running on port 3000
```

---

## 🌐 Production Deployment

Deploy the full stack behind the preconfigured Nginx proxy:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

*   **API Docs:** `/docs` (Auto-generated OpenAPI)
*   **Monitoring:** `/flower/` (Celery task tracker)
*   **Health Checks:** `/health` (System status for Redis, MongoDB, and Chroma)
