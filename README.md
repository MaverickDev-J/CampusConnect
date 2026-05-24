# 🎓 CampusMind — The AI-Powered Academic Hub

> **Status**: 🚀 Fully Operational. *From static PDFs to interactive knowledge in seconds.*

---

## ✨ Experience Modern Academic AI
CampusMind is a premium, bento-style classroom platform designed to turn your study materials into a living, breathing knowledge base. It bridge the gap between static files and deep understanding using the latest in **Google Gemini AI** and **LaTeX-ready** math rendering.

---

## 🌟 Premium Features

### 🧠 AI-Powered Study Assistant
Not just a chatbot, but a specialized tutor for your classroom.
- **KaTeX Professional Math**: Beautiful, human-readable math notation ($\sigma(z)$ vs `$$\sigma(z)$$`).
- **Contextual Ingestion**: AI "reads" your PDFs and images to provide exact page citations.
- **Recent Material Awareness**: Deep integration with MongoDB to prioritize your latest uploads.

### 🍱 Bento-Style Dashboard
A stunning, glassmorphic interface that puts your learning first.
- **Classroom Cards**: Quick access to your academic hubs with instructor visibility.
- **Glassmorphic UI**: Sophisticated blur effects and a lightweight, premium feel.
- **Confetti Celebrations**: Modern micro-interactions for successful uploads and actions.

### ⚙️ High-Performance Engine
Built on a "state-of-the-art" technical foundation:
- **FastAPI Backend**: Rapid, scalable Python-based API.
- **Celery Worker Ingestion**: Asynchronous file processing for a lag-free experience.
- **Vector Search (ChromaDB)**: Lightning-fast retrieval of academic context.
- **Google Gemini 1.5**: Support for multi-modal context (Text + Images + Math).

---

## 🏗️ Technical Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | Next.js 15+, React 19, Tailwind CSS 4, Framer Motion |
| **Backend** | FastAPI, Python 3.10+, Celery, Redis |
| **AI/ML** | Google Gemini (Flash-Lite), ChromaDB, KaTeX Rendering |
| **Database** | MongoDB (NoSQL), Redis (Caching) |

---

## 🚀 Quick Start

### 🔧 Prerequisites
- **Node.js** (v20+)
- **Python** (v3.10+)
- **MongoDB** & **Redis** (Local or Cloud)
- **Google Gemini API Key**

### 💻 Local Development

1. **Backend Setup**:
   ```bash
   cd backend
   pip install -r requirements.txt
   # Setup .env with Gemini/Mongo keys
   python run.py
   ```

2. **Frontend Setup**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. **Background Workers**:
   ```bash
   cd backend
   celery -A core.worker worker --loglevel=info
   ```

---

## 📚 Learn More
For a detailed log of the project's evolution and all implemented features from day one, see:
👉 **[The Full Update Timeline (UPDATES.md)](./UPDATES.md)**

---

##  Summary
CampusMind is more than a classroom hub; it’s an **intelligent ecosystem** for students and teachers. It combines a premium user experience with powerful AI automation to make learning more efficient, interactive, and visually stunning.
