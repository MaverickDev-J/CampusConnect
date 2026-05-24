# 📚 CampusMind — Development Run Guide

This guide contains the verified commands and configuration steps to run the full **CampusMind** academic stack locally.

---

## 🐳 Step 1: Start Infrastructure (Docker)

All database and caching services run in Docker containers. Ensure **Docker Desktop** is running first.

```powershell
# From the project root (CampusMind-main/)
docker-compose up -d
```

| Service | Port | Browse To |
|---|---|---|
| **MongoDB 7.0** | `27017` | Use MongoDB Compass |
| **Redis Stack** | `6379` | Internal Cache |
| **Mongo Express** | `8081` | [http://localhost:8081](http://localhost:8081) |

> **Credentials**: `admin` / `campusadmin` (Express) | `campusadmin` / `campuspass123` (DB)

---

## 🐍 Step 2: Run the FastAPI Backend

The backend handles the AI RAG logic and API orchestration.

```powershell
cd backend
# Recommended: Use 'uv' for fast, isolated execution
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- **Open Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## ⚙️ Step 3: Run the Celery AI Worker

The worker handles heavy-duty PDF and image ingestion in the background.

```powershell
# In a new terminal
cd backend
uv run celery -A core.celery_app worker --loglevel=info -P solo
```

> **Note**: The `-P solo` flag is required for Windows stability when running deep learning models like Docling locally.

---

## 🌐 Step 4: Run the Frontend (Next.js)

The premium, glassmorphic student dashboard and chat interface.

```powershell
cd frontend
# First-time setup (installs math rendering & motion libs)
npm install
npm run dev
```

- **Dashboard**: [http://localhost:3000](http://localhost:3000)

---

## 🔑 AI & Environment Setup

Ensure your `backend/.env` file is configured with valid **Google Gemini API Keys**.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEYS` | **Primary Pool**: Comma-separated keys (Shared for all tasks). |
| `GEMINI_ROUTER_KEYS` | **Classification**: Dedicated pool for fast routing. |
| `GEMINI_CHAT_KEYS` | **Conversation**: Dedicated pool for high-fidelity chat response. |
| `GEMINI_INGESTION_KEYS` | **Heavy-Duty**: Dedicated pool for multi-page PDF/Image processing. |

---

## 🔧 Troubleshooting

| Problem | Solution |
|---|---|
| `Module not found: react-markdown` | Run `npm install` in the frontend directory. |
| `SyntaxWarning: invalid escape \e` | No longer an issue; ensure you are on the latest `api/agent/nodes.py`. |
| `Math equations not rendering` | Ensure `katex` styles are imported in `frontend/app/globals.css`. |
| `AI answers but no context` | Confirm the Celery worker (Step 3) processed the file successfully. |
| `MongoDB auth failed` | Check that `MONGO_URI` matches the credentials in Step 1. |

---

---
© 2026 CampusMind Project. All documentation is current as of the latest **Optimization Phase**.