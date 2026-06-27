# 🧠 CareerMind AI

> **Your AI-powered career intelligence platform** — From raw resume to job-ready in one session.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://react.dev)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.1-purple.svg)](https://langchain-ai.github.io/langgraph/)
[![Gemini](https://img.shields.io/badge/Gemini-1.5_Flash-orange.svg)](https://ai.google.dev)

---

## 📋 Project Overview

CareerMind AI is a **production-grade, multi-agent AI career coach platform** built for fresh graduates and job seekers in tech. It orchestrates four specialized AI agents via LangGraph to:

1. **Analyze** your resume with Gemini + RAG (skill detection, ATS scoring, gap analysis)
2. **Match** live job listings from JSearch + Adzuna with AI fit scoring
3. **Rewrite** your resume for a specific role using Gemini
4. **Interview** you with adaptive voice questions, Whisper transcription, and Gemini scoring

**Target users:** CS/AI/SWE graduates entering the job market  
**Goal:** Transform a raw resume into job applications + interview readiness in under 60 minutes

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        CareerMind AI                             │
├──────────────────┬───────────────────────────────────────────────┤
│  Frontend        │  React 18 + Vite + Tailwind CSS v3            │
│  (Port 3000)     │  Framer Motion · Zustand · React Router v6    │
├──────────────────┼───────────────────────────────────────────────┤
│  REST + WebSocket│  FastAPI (Port 8000)                          │
├──────────────────┴───────────────────────────────────────────────┤
│             LangGraph Supervisor StateGraph                       │
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │Resume Analyzer│──▶│  Job Scraper │──▶│   Resume Rewriter    │ │
│  │ PyPDF2+Gemini │   │ JSearch+     │   │    Gemini + diff     │ │
│  │ ChromaDB RAG  │   │ Adzuna+score │   └──────────────────────┘ │
│  └──────────────┘   └──────────────┘           │                │
│                                                 ▼                │
│                                    ┌──────────────────────────┐  │
│                                    │    Mock Interviewer       │  │
│                                    │ Gemini + Whisper + gTTS  │  │
│                                    └──────────────────────────┘  │
│                                                                  │
│  ChromaDB (local vector store)  ·  SQLite (sessions)            │
│  LangSmith (agent tracing)      ·  WebSocket (live events)      │
└──────────────────────────────────────────────────────────────────┘
```

---

## ✨ Features

| Agent | What it does |
|-------|-------------|
| 🔍 **Resume Analyzer** | Extracts PDF text, runs RAG over skills KB, returns score/gaps/suggestions via Gemini |
| 💼 **Job Scraper** | Fetches live jobs from JSearch + Adzuna, scores each against your profile in parallel |
| ✏️ **Resume Rewriter** | Rewrites your resume for a specific role, adds keywords, quantifies achievements |
| 🎤 **Mock Interviewer** | Generates adaptive questions, transcribes voice via Whisper, scores with Gemini |
| 🧠 **LangGraph Supervisor** | Orchestrates all agents, streams real-time events over WebSocket |

---

## 🛠️ Tech Stack

| Tool | Purpose | Cost |
|------|---------|------|
| **Gemini 1.5 Flash** | LLM for all AI tasks | Free (15 RPM, 1M tok/day) |
| **LangChain + LangGraph** | Agent orchestration | Free/Open Source |
| **ChromaDB** | Local vector database (RAG) | Free/Local |
| **openai-whisper** | Offline speech-to-text | Free/Local |
| **gTTS** | Text-to-speech for questions | Free |
| **FastAPI** | REST API + WebSocket server | Free |
| **PyPDF2** | PDF text extraction | Free |
| **SQLite + aiosqlite** | Session persistence | Free/Local |
| **LangSmith** | Agent tracing + observability | Free (dev tier) |
| **JSearch (RapidAPI)** | Live job listings | 100 req/day free |
| **Adzuna API** | Backup job source | 250 req/day free |
| **React 18 + Vite** | Frontend framework | Free |
| **Tailwind CSS v3** | Styling | Free |
| **Framer Motion** | Animations | Free |
| **Zustand** | State management | Free |

---

## 🔑 Free API Setup

### 1. Google Gemini API (Required)
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **Get API Key** → Create API key
3. Copy the key → set as `GOOGLE_API_KEY` in `.env`
4. Free tier: 15 RPM, 1M tokens/day

### 2. LangSmith (Optional — for tracing)
1. Go to [smith.langchain.com](https://smith.langchain.com)
2. Sign up (free) → Settings → API Keys → Create
3. Set `LANGCHAIN_API_KEY` in `.env`
4. Set `LANGCHAIN_TRACING_V2=true`

### 3. JSearch via RapidAPI (Optional)
1. Go to [rapidapi.com](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
2. Subscribe to free tier (100 req/day)
3. Copy API key → set as `RAPIDAPI_KEY` in `.env`
4. Falls back to Adzuna automatically if limit hit

### 4. Adzuna API (Optional)
1. Go to [developer.adzuna.com](https://developer.adzuna.com)
2. Register → Create App → Get App ID + Key
3. Set `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` in `.env`
4. 250 free requests/day

> **Note:** The app works without job API keys — it uses realistic demo job data as fallback.

---

## 🚀 Local Development

### Quick Start

```bash
# Terminal 1 — Backend
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then add GOOGLE_API_KEY
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm install
npm run dev

# Verify backend is working:
# Open browser → http://localhost:8000/health
# Should show all ✅ green

# Verify frontend API connection:
# Open browser console → Network tab
# All /api/ calls should return 200, not 502
```

### Prerequisites
- Python 3.11+
- Node.js 18+
- `ffmpeg` (required for Whisper): `brew install ffmpeg` on macOS

### 1. Clone & Setup
```bash
git clone <repo-url>
cd careermind-ai
```

### 2. Backend
```bash
cd backend

# Copy and fill environment variables
cp .env.example .env
# Edit .env with your API keys

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start backend
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`  
API docs: `http://localhost:8000/docs`

### 3. Frontend
```bash
# In a new terminal
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

The frontend will be at `http://localhost:3000`

### 4. Verify
Open `http://localhost:3000` in your browser. The agent panel should show "Connected" (green dot).


---

## 🐳 Docker Setup

```bash
# Copy env file
cp backend/.env.example .env
# Edit .env with your API keys

# Build and run everything
docker-compose up --build

# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
# API docs: http://localhost:8000/docs
```

---

## 📡 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/token` | Generate JWT token |
| `POST` | `/api/upload-resume` | Upload PDF, returns file_path |
| `POST` | `/api/analyze` | Run resume analysis |
| `GET` | `/api/jobs?q=&location=` | Fetch + score job listings |
| `POST` | `/api/rewrite` | Rewrite resume for job |
| `POST` | `/api/interview/question` | Generate interview question + TTS |
| `POST` | `/api/interview/score` | Score audio/text answer |
| `GET` | `/api/session/{user_id}` | Get full session state |
| `GET` | `/api/health` | Health check |
| `WS` | `/ws/agent-stream` | Real-time agent event stream |

---

## 📊 LangSmith Traces

When `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` are set, all LangGraph agent runs are automatically traced at [smith.langchain.com](https://smith.langchain.com).

Project name: `careermind-ai`

---

## 🗂️ Project Structure

```
careermind-ai/
├── backend/
│   ├── main.py              # FastAPI app (8 endpoints + WebSocket)
│   ├── config.py            # Gemini LLM + embeddings config
│   ├── db.py                # SQLite async session layer
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env.example
│   ├── agents/
│   │   ├── supervisor.py    # LangGraph StateGraph
│   │   ├── resume_analyzer.py
│   │   ├── job_scraper.py
│   │   ├── resume_rewriter.py
│   │   └── mock_interviewer.py
│   ├── tools/
│   │   ├── chromadb_tool.py # SkillsVectorStore + ResumeVectorStore
│   │   ├── jsearch_tool.py  # JSearch API integration
│   │   ├── adzuna_tool.py   # Adzuna fallback + demo jobs
│   │   └── whisper_tool.py  # Offline STT singleton
│   └── data/
│       ├── skills_kb/       # RAG knowledge base files
│       └── uploads/         # Uploaded PDFs
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Router + AnimatePresence
│   │   ├── pages/           # 6 pages with Framer Motion
│   │   ├── components/      # 7 reusable components
│   │   ├── hooks/           # useAgentStream + useVoiceRecorder
│   │   ├── store/           # Zustand global store
│   │   └── lib/api.js       # Axios API client
│   ├── tailwind.config.js   # Design tokens
│   └── Dockerfile
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## 🌐 Deployment

### Backend → Render.com
1. Connect your GitHub repo to Render
2. New **Web Service** → select `backend/` directory
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add all `.env` variables in Render environment settings
6. Note: Whisper requires ffmpeg — add `apt-get install -y ffmpeg` in a render build script

### Frontend → Vercel
1. Import repo → set **Root Directory** to `frontend/`
2. Framework preset: **Vite**
3. Add `VITE_API_URL` env var pointing to your Render backend URL
4. Deploy — done!

---

## 📝 Resume Bullet Points

Copy-paste for your own resume after building this project:

```
• Built CareerMind AI, a production-grade multi-agent AI career platform using LangGraph,
  Gemini 1.5 Flash, FastAPI, and React 18 that analyzes resumes, matches live jobs, and
  conducts voice mock interviews — reducing manual job prep time by ~80%

• Architected a LangGraph StateGraph orchestrating 4 specialized AI agents with real-time
  WebSocket event streaming, parallel job scoring (asyncio.gather), and ChromaDB RAG
  retrieval over a 3-domain skills knowledge base

• Implemented full-stack AI pipeline: PyPDF2 PDF parsing → Gemini structured analysis →
  JSearch/Adzuna job scraping → Gemini match scoring → Whisper STT → gTTS TTS, with
  graceful fallbacks at every stage for zero-downtime operation

• Designed a premium React/Tailwind UI with 6 animated pages (Framer Motion AnimatePresence),
  real-time agent activity panel (WebSocket), voice recorder with waveform visualization,
  and animated SVG score rings
```

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit: `git commit -m 'Add amazing feature'`
4. Push: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 🔥 Firebase Console Setup Checklist

To enable real authentication and Google login in development and production, complete the following:

1. **Create Firebase Project**:
   * Go to [firebase.google.com](https://firebase.google.com/) and click **Go to console** → **Add project**.
   * Name your project (e.g., `careermind-ai`).
2. **Add a Web App**:
   * Click the **Web** icon (`</>`) to add an app.
   * Copy the `firebaseConfig` credentials from the setup script.
   * Paste these credentials into `frontend/.env` using the corresponding `VITE_FIREBASE_*` keys.
3. **Enable Auth Sign-In Methods**:
   * In the sidebar, go to **Build** → **Authentication** and click **Get Started**.
   * Go to the **Sign-in method** tab:
     * Enable **Email/Password** and click **Save**.
     * Enable **Google**, select a project support email, and click **Save**.
4. **Authorized Domains**:
   * Under **Authentication** → **Settings** → **Authorized domains**:
     * `localhost` and `127.0.0.1` are enabled by default for local development.
     * Add your hosting domain (e.g., `careermind-ai.vercel.app`) when deploying.
5. **Google Cloud Consent Screen**:
   * Go to the [Google Cloud Console](https://console.cloud.google.com/).
   * Select your Firebase project from the top dropdown.
   * Navigate to **APIs & Services** → **OAuth consent screen**.
   * Fill out the **App name** ("CareerMind AI") and **User support email**, then save and finish all steps.

---

## 📄 License

MIT License — free for personal and commercial use.

---

*Built with 🧠 LangGraph · ⚡ Gemini · 🚀 FastAPI · ⚛️ React*

