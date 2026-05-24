# 🚀 CampusConnect — Complete Local Run Guide

> **Status**: Current as of CampusConnect v2.0 (with Demo Mode, LangGraph, Celery, Redis, ChromaDB)

---

## ⚠️ Prerequisites — What You Need Installed

| Tool | Why | Install |
|------|-----|---------|
| **Docker Desktop** | Runs MongoDB, Redis, ChromaDB | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| **uv** (Python pkg manager) | Runs the FastAPI backend & Celery | `pip install uv` |
| **Node.js 18+** | Runs the Next.js frontend | [nodejs.org](https://nodejs.org/) |

> **Docker is required** — Redis, MongoDB, and ChromaDB all run as Docker containers.  
> If Docker Desktop is not running, start it first before running any commands below.

---

## 📝 Step 0: Fix Your `.env` File

Your `backend/.env` currently has issues. Replace it with this (already has your keys):

```env
# ── Gemini AI ────────────────────────────────────────────────────
GEMINI_API_KEY=AIzaSyB...your-key-here

# Use same key for all pools (or add separate keys for each if you have them)
GEMINI_API_KEYS=AIzaSyB...your-key-here
GEMINI_ROUTER_KEYS=AIzaSyB...your-key-here
GEMINI_CHAT_KEYS=AIzaSyB...your-key-here
GEMINI_INGESTION_KEYS=AIzaSyB...your-key-here

# ── JWT ──────────────────────────────────────────────────────────
JWT_SECRET=1031e5f769e525f6497f2083fc41b9ade0545bfa71189d586ee8f107cb951485

# ── MongoDB (Docker local) ───────────────────────────────────────
MONGO_URI=mongodb://campusadmin:campuspass123@localhost:27017/campusconnect?authSource=admin
MONGO_DB=campusconnect

# ── Redis (Docker local) ─────────────────────────────────────────
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

# ── ChromaDB (Docker local) ──────────────────────────────────────
CHROMA_HOST=localhost
CHROMA_PORT=8100

# ── Superadmin ───────────────────────────────────────────────────
SUPERADMIN_EMAIL=superadmin@campusconnect.local
SUPERADMIN_PASSWORD=Admin@12345
```

---

## 🐳 Step 1: Start Docker Services

**Make sure Docker Desktop is running first**, then open a terminal in the project root:

```powershell
# From: c:\Users\jatin\Desktop\CampusConnect\
docker-compose up -d
```

**Wait ~30 seconds** for all services to become healthy, then verify:

```powershell
docker-compose ps
```

You should see all 4 containers as **running**:

| Container | Port | Purpose |
|-----------|------|---------|
| `campusconnect_mongo` | `27017` | MongoDB database |
| `campusconnect_redis` | `6379` | Redis (cache + broker + PubSub) |
| `campusconnect_chroma` | `8100` | ChromaDB vector store |
| `campusconnect_mongo_express` | `8081` | MongoDB admin UI (optional) |

> **MongoDB Admin UI**: http://localhost:8081 → login: `admin` / `campusadmin`

---

## 🐍 Step 2: Start the FastAPI Backend

Open a **new terminal window** (keep the Docker one open):

```powershell
cd c:\Users\jatin\Desktop\CampusConnect\backend
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

✅ **Success signs** in the terminal:
```
[OK] MongoDB connected & all indexes ensured
[OK] ChromaDB connected (campus_vectors collection ready)
[OK] Rate limiting enabled
[SEED] Superadmin created: superadmin@campusconnect.local
INFO: Application startup complete.
```

- **API Docs**: http://127.0.0.1:8000/docs
- **Health Check**: http://127.0.0.1:8000/health

---

## ⚙️ Step 3: Start the Celery Worker (PDF Processing)

Open another **new terminal window**:

```powershell
cd c:\Users\jatin\Desktop\CampusConnect\backend
uv run celery -A core.celery_app.celery_app worker --loglevel=info -P solo
```

✅ **Success signs**:
```
[Celery] Worker initialized: MongoDB + ChromaDB connections ready
celery@your-machine ready.
```

> **`-P solo` is required on Windows** — Celery's default process pool crashes on Windows with ML models (Docling). Solo mode is stable and correct.

---

## 🌐 Step 4: Start the Frontend (Next.js)

Open another **new terminal window**:

```powershell
cd c:\Users\jatin\Desktop\CampusConnect\frontend

# First time only — install dependencies
npm install

# Start dev server
npm run dev
```

✅ **Success sign**:
```
▲ Next.js 15.x.x
- Local: http://localhost:3000
```

---

## 🎯 The Full System is Now Running

Open **http://localhost:3000** in your browser.

| What you see | Means |
|---|---|
| Landing page with "Try Live Demo" | ✅ System working perfectly |
| Login page | ✅ Also fine — click login |
| Error / blank page | ❌ Check the FastAPI terminal for errors |

### Quick Demo Test
1. Go to http://localhost:3000
2. Click **"Try Live Demo — No Sign Up"**
3. You'll be logged in as a demo student with a pre-loaded AI classroom
4. Ask: *"How does the semantic cache work?"*

### Login as Superadmin
- **Email**: `superadmin@campusconnect.local`
- **Password**: `Admin@12345`

---

## 🪟 Terminal Layout (4 Terminals Total)

```
Terminal 1: docker-compose up -d        ← Infrastructure
Terminal 2: uv run uvicorn main:app ... ← Backend API (port 8000)
Terminal 3: uv run celery ...           ← Worker (PDF processing)
Terminal 4: npm run dev                 ← Frontend (port 3000)
```

---

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| `Docker not running` | Open Docker Desktop and wait for it to fully start |
| `MongoServerError: Authentication failed` | Check your `MONGO_URI` in `.env` matches Step 0 exactly |
| `Connection refused: 6379` | Redis container not running — run `docker-compose up -d redis` |
| `Connection refused: 8100` | ChromaDB not running — run `docker-compose up -d chromadb` |
| `JWT_SECRET is missing or insecure` | Your `.env` needs `JWT_SECRET` with 32+ chars |
| `Celery worker crashes immediately` | Make sure you're using `-P solo` flag |
| `npm install fails` | Run `node --version` — needs Node 18+ |
| `Module not found: framer-motion` | Run `npm install` in the `frontend/` folder |
| `Demo login fails` | Check backend terminal — Gemini API key may be invalid/expired |
| Frontend shows blank white page | Check browser console (F12) for errors; check if backend is on port 8000 |
| `Cannot find file: ChromaDB` | Old CampusMind embedded mode — CampusConnect uses Docker HTTP mode, that's fine |

---

## 🛑 Stopping Everything

```powershell
# Stop Docker services (keeps data)
docker-compose stop

# Stop Docker AND delete all data (fresh start)
docker-compose down -v
```

To stop the FastAPI, Celery, and Next.js processes: press `Ctrl+C` in each terminal.

---

## 📁 Project Structure Quick Reference

```
CampusConnect/
├── backend/          ← FastAPI app (run with uv)
│   ├── .env          ← YOUR CONFIG FILE (edit this)
│   ├── main.py       ← App entry point
│   └── api/routers/  ← All API routes including demo.py
├── frontend/         ← Next.js app (run with npm)
│   └── app/          ← All pages and components
├── docker-compose.yml ← MongoDB + Redis + ChromaDB
└── RUN_GUIDE.md      ← This file
```

---

*© 2026 CampusConnect — Updated for v2.0 with Demo Mode, LangGraph Pipeline, Celery Workers, Redis Caching, ChromaDB Server Mode.*