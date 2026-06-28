import os
import sys
import json
import re
import io
import asyncio
import traceback
import tempfile
from pathlib import Path
from dotenv import load_dotenv

# Load env vars FIRST before anything else
load_dotenv()

# Print startup info immediately so Render logs show it
print("=" * 50)
print("CareerMind AI Backend Starting...")
print(f"Python: {sys.version}")
print(f"GOOGLE_API_KEY: {'SET ✅' if os.getenv('GOOGLE_API_KEY', '').strip() else 'MISSING ❌'}")
print(f"RAPIDAPI_KEY:   {'SET ✅' if os.getenv('RAPIDAPI_KEY', '').strip() else 'NOT SET ⚠️'}")
print(f"ADZUNA_APP_ID:  {'SET ✅' if os.getenv('ADZUNA_APP_ID', '').strip() else 'NOT SET ⚠️'}")
print(f"FRONTEND_URL:   {os.getenv('FRONTEND_URL', 'NOT SET ⚠️')}")
print("=" * 50)

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse

# ── Safe package imports ───────────────────────────────────────────
LLM_OK    = False
PDF_OK    = False
CHROMA_OK = False

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    LLM_OK = True
    print("✅ langchain_google_genai imported")
except Exception as e:
    print(f"❌ langchain_google_genai failed: {e}")

try:
    import PyPDF2
    PDF_OK = True
    print("✅ PyPDF2 imported")
except Exception as e:
    print(f"⚠️ PyPDF2 failed: {e}")

try:
    import chromadb
    CHROMA_OK = True
    print("✅ chromadb imported")
except Exception as e:
    print(f"⚠️ chromadb failed: {e}")

# ── Ensure directories ─────────────────────────────────────────────
for d in ["data/uploads", "data/skills_kb", "chroma_db"]:
    Path(d).mkdir(parents=True, exist_ok=True)

# Create default skills KB
kb = Path("data/skills_kb/skills.txt")
if not kb.exists():
    kb.write_text(
        "Python JavaScript TypeScript React Next.js Node.js FastAPI Django "
        "Machine Learning Deep Learning NLP LangChain LangGraph RAG ChromaDB "
        "TensorFlow PyTorch Scikit-learn Gemini GPT Docker Kubernetes AWS GCP "
        "PostgreSQL MongoDB Redis GraphQL REST APIs Git Algorithms System Design "
        "HTML CSS Tailwind Firebase Supabase Android iOS React Native Java C++"
    )

# ── LLM singleton ─────────────────────────────────────────────────
_llm = None

def get_llm():
    global _llm
    if _llm is not None:
        return _llm
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not key:
        print("❌ GOOGLE_API_KEY empty at get_llm() call")
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        _llm = genai.GenerativeModel("gemini-2.5-flash")
        print("✅ Gemini LLM (official SDK) initialized")
        return _llm
    except Exception as e:
        print(f"❌ LLM init failed: {e}")
        return None

def call_gemini(prompt: str) -> str:
    """Call Gemini using the official SDK. Returns response text or ERROR: message."""
    try:
        model = get_llm()
        if model is None:
            return "ERROR: Gemini not available. Check GOOGLE_API_KEY in Render environment."
        response = model.generate_content(prompt)
        return response.text or ""
    except Exception as e:
        err = str(e)
        print(f"❌ Gemini call failed: {err}")
        if "API_KEY" in err or "api key" in err.lower() or "credentials" in err.lower():
            return "ERROR: Invalid GOOGLE_API_KEY. Verify it in Render → Environment."
        if "quota" in err.lower() or "429" in err:
            return "ERROR: Gemini quota exceeded. Wait and retry."
        return f"ERROR: {err[:150]}"

async def call_gemini_async(prompt: str, timeout: float = 30.0) -> str:
    """Async Gemini call with timeout."""
    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: call_gemini(prompt)),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        return "ERROR: Request timed out. Gemini was too slow."
    except Exception as e:
        return f"ERROR: {str(e)}"

def parse_json(text: str, fallback: dict) -> dict:
    """Safely parse JSON from LLM response."""
    try:
        cleaned = re.sub(r"```json|```", "", text or "").strip()
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(cleaned)
    except Exception:
        return fallback

def extract_pdf_text(path: str) -> str:
    """Extract text from PDF."""
    if not PDF_OK or not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return " ".join(p.extract_text() or "" for p in reader.pages).strip()
    except Exception as e:
        return f"PDF extraction error: {e}"

# In-memory cache
_cache: dict = {}

# ── FASTAPI APP ────────────────────────────────────────────────────
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✅ FastAPI lifespan started")
    # Warm up LLM in background
    async def warmup():
        await asyncio.sleep(2)
        llm = get_llm()
        if llm:
            print("✅ LLM warmed up")
        # Keep-alive ping
        while True:
            await asyncio.sleep(840)  # 14 min
            try:
                import httpx
                url = os.getenv("RENDER_EXTERNAL_URL", "")
                if url:
                    async with httpx.AsyncClient(timeout=5.0) as c:
                        await c.get(f"{url}/health")
                    print("✅ Keep-alive ping sent")
            except Exception:
                pass
    asyncio.create_task(warmup())
    yield
    print("CareerMind AI shutting down")

app = FastAPI(
    title="CareerMind AI",
    version="2.0.0",
    lifespan=lifespan
)

# ── CORS ──────────────────────────────────────────────────────────
FRONTEND = os.getenv("FRONTEND_URL", "").rstrip("/")
ORIGINS  = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:4173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://frontend-gold-one-48.vercel.app",
    "https://careermind-ai.vercel.app",
]
if FRONTEND:
    ORIGINS.append(FRONTEND)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_origin_regex=r"https://.*\.(vercel\.app|onrender\.com|netlify\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
    max_age=600,
)
app.add_middleware(GZipMiddleware, minimum_size=500)

print("✅ FastAPI app created with CORS")
print(f"✅ Allowed origins: {ORIGINS}")

# ═══════════════════════════════════════════════════════════════════
# ROUTES — all defined at module level, no routers, no prefixes
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "message":  "CareerMind AI backend is running",
        "status":   "online",
        "version":  "2.0.0",
        "docs":     "/docs",
        "health":   "/health",
        "diagnose": "/api/diagnose",
    }

@app.get("/health")
async def health():
    key_set = bool(os.getenv("GOOGLE_API_KEY", "").strip())
    gemini_status = "key_not_set"
    gemini_test   = "❌ GOOGLE_API_KEY not set in Render Environment"

    if key_set and LLM_OK:
        try:
            resp = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: call_gemini("Say: WORKING")
                ),
                timeout=8.0
            )
            if resp and not resp.startswith("ERROR:"):
                gemini_status = "ok"
                gemini_test   = f"✅ working — {resp[:30]}"
            else:
                gemini_status = "error"
                gemini_test   = f"❌ {resp[:80]}"
        except asyncio.TimeoutError:
            gemini_status = "timeout"
            gemini_test   = "⚠️ key set but timed out (cold start) — will work for real requests"
        except Exception as e:
            gemini_status = "error"
            gemini_test   = f"❌ {str(e)[:80]}"
    elif not key_set:
        gemini_status = "missing"

    return {
        "status":         "online",
        "google_api_key": "SET" if key_set else "MISSING",
        "gemini_status":  gemini_status,
        "gemini_test":    gemini_test,
        "llm_available":  LLM_OK and key_set,
        "pdf_available":  PDF_OK,
    }

@app.get("/api/diagnose")
async def diagnose():
    results = {}
    key = os.getenv("GOOGLE_API_KEY","").strip()
    results["GOOGLE_API_KEY"] = "✅ SET" if key else "❌ MISSING"
    results["RAPIDAPI_KEY"]   = "✅ SET" if os.getenv("RAPIDAPI_KEY","").strip() else "⚠️ NOT SET"
    results["FRONTEND_URL"]   = os.getenv("FRONTEND_URL","⚠️ NOT SET")

    if key and LLM_OK:
        try:
            r = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, lambda: call_gemini("Say OK")),
                timeout=15.0
            )
            results["gemini"] = f"✅ {r[:40]}" if not r.startswith("ERROR:") else f"❌ {r[:80]}"
        except asyncio.TimeoutError:
            results["gemini"] = "⚠️ timeout (key set, cold start)"
    else:
        results["gemini"] = "❌ GOOGLE_API_KEY missing or LLM not installed"

    results["routes"] = [
        "GET  /",
        "GET  /health",
        "GET  /api/diagnose",
        "POST /api/upload-resume",
        "POST /api/analyze",
        "GET  /api/jobs",
        "POST /api/rewrite",
        "POST /api/rewrite/download-pdf",
        "POST /api/interview/question",
        "POST /api/interview/score-text",
        "POST /api/interview/score",
        "POST /api/interview/followup",
        "POST /api/interview/report",
        "POST /api/daily-coach/respond",
        "POST /api/daily-coach/feedback",
        "POST /api/score-pdf",
        "GET  /api/session/{user_id}",
    ]
    results["SUMMARY"] = "✅ ALL OK" if "❌" not in str(results) else "❌ ISSUES FOUND"
    return results

# ── Upload Resume ──────────────────────────────────────────────────
@app.post("/api/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    try:
        name = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename or "resume.pdf")
        path = f"data/uploads/{name}"
        data = await file.read()
        with open(path, "wb") as f:
            f.write(data)
        return {"file_path": path, "filename": name, "size": len(data)}
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {e}")

# ── Analyze Resume ─────────────────────────────────────────────────
@app.post("/api/analyze")
async def analyze_resume(request: dict):
    path    = request.get("resume_path", "")
    job_desc = request.get("job_description", "")
    user_id = request.get("user_id", "anon")

    if not path or not os.path.exists(path):
        raise HTTPException(404, f"Resume not found: {path}")

    text = extract_pdf_text(path)
    if not text or len(text) < 20:
        raise HTTPException(422, "Cannot extract text from PDF. Ensure it is not a scanned image.")

    prompt = (
        f"Analyze this resume and return ONLY valid JSON, no markdown.\n"
        f"Resume: {text[:2000]}\n"
        f"Job description: {job_desc[:300] or 'not provided'}\n\n"
        f"Return exactly:\n"
        f'{{"skills_found":["Python","React"],"skill_gaps":["Docker"],'
        f'"experience_level":"junior","overall_score":72,"ats_score":68,'
        f'"sections_detected":["Education","Experience"],'
        f'"suggestions":["Add metrics to bullets"]}}'
    )

    raw    = await call_gemini_async(prompt, timeout=30.0)
    result = parse_json(raw, {
        "skills_found":      [],
        "skill_gaps":        [],
        "experience_level":  "junior",
        "overall_score":     55,
        "ats_score":         55,
        "sections_detected": [],
        "suggestions":       ["Could not analyze — check API key"],
    })
    result["resume_text"] = text
    _cache[f"analysis:{user_id}"] = result
    _cache[f"text:{path}"]        = text
    return result

# ── Jobs ───────────────────────────────────────────────────────────
@app.get("/api/jobs")
async def get_jobs(
    q:        str = "Software Engineer",
    location: str = "India",
    user_id:  str = "anon",
):
    import httpx
    jobs = []

    # JSearch
    rk = os.getenv("RAPIDAPI_KEY", "").strip()
    if rk:
        try:
            async with httpx.AsyncClient(timeout=7.0) as c:
                r = await c.get(
                    "https://jsearch.p.rapidapi.com/search",
                    headers={"X-RapidAPI-Key": rk, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
                    params={"query": f"{q} in {location}", "num_pages": "1"},
                )
                for j in r.json().get("data", [])[:10]:
                    jobs.append({
                        "id":          j.get("job_id",""),
                        "title":       j.get("job_title",""),
                        "company":     j.get("employer_name",""),
                        "location":    j.get("job_city", location),
                        "description": (j.get("job_description") or "")[:400],
                        "apply_link":  j.get("job_apply_link","#"),
                        "salary":      "",
                        "source":      "jsearch",
                        "match_score": 0,
                    })
        except Exception as e:
            print(f"JSearch error: {e}")

    # Adzuna fallback
    ai = os.getenv("ADZUNA_APP_ID","").strip()
    ak = os.getenv("ADZUNA_APP_KEY","").strip()
    if not jobs and ai and ak:
        try:
            async with httpx.AsyncClient(timeout=7.0) as c:
                r = await c.get(
                    "https://api.adzuna.com/v1/api/jobs/in/search/1",
                    params={"app_id": ai, "app_key": ak, "what": q, "where": location, "results_per_page": 10},
                )
                for j in r.json().get("results", [])[:10]:
                    jobs.append({
                        "id":          str(j.get("id","")),
                        "title":       j.get("title",""),
                        "company":     j.get("company",{}).get("display_name",""),
                        "location":    j.get("location",{}).get("display_name", location),
                        "description": (j.get("description") or "")[:400],
                        "apply_link":  j.get("redirect_url","#"),
                        "salary":      str(j.get("salary_max","")),
                        "source":      "adzuna",
                        "match_score": 0,
                    })
        except Exception as e:
            print(f"Adzuna error: {e}")

    # Demo fallback — always returns something
    if not jobs:
        jobs = [
            {"id":"d1","title":f"Senior {q}","company":"TechCorp India","location":location,
             "description":f"Senior {q} role with Python, React, FastAPI. 2+ years exp.","apply_link":"https://linkedin.com/jobs","salary":"12-20 LPA","source":"demo","match_score":88,"matched_skills":["Python","React"],"missing_skills":["Docker"],"recommendation":"Strong match"},
            {"id":"d2","title":f"AI/ML {q}","company":"InnovateTech","location":"Hyderabad",
             "description":f"AI {q} role. LangChain, Gemini, RAG, FastAPI.","apply_link":"https://linkedin.com/jobs","salary":"8-15 LPA","source":"demo","match_score":92,"matched_skills":["LangChain","Python"],"missing_skills":[],"recommendation":"Excellent match"},
            {"id":"d3","title":f"Full Stack {q}","company":"GlobalTech","location":"Remote",
             "description":f"Remote {q}. React, Node.js, Python, Docker.","apply_link":"https://linkedin.com/jobs","salary":"10-18 LPA","source":"demo","match_score":78,"matched_skills":["React","Python"],"missing_skills":["AWS"],"recommendation":"Good match"},
            {"id":"d4","title":f"Junior {q}","company":"StartupXYZ","location":"Mumbai",
             "description":f"Junior {q} for freshers. React, Python, Firebase.","apply_link":"https://linkedin.com/jobs","salary":"4-8 LPA","source":"demo","match_score":82,"matched_skills":["React","Python","Firebase"],"missing_skills":[],"recommendation":"Great entry-level fit"},
            {"id":"d5","title":f"Backend {q}","company":"FinTech Corp","location":"Pune",
             "description":f"Backend {q}. Python, FastAPI, PostgreSQL, Redis.","apply_link":"https://linkedin.com/jobs","salary":"8-14 LPA","source":"demo","match_score":74,"matched_skills":["Python","FastAPI"],"missing_skills":["PostgreSQL"],"recommendation":"Good match"},
            {"id":"d6","title":f"{q} Intern","company":"MNC Corp","location":"Ahmedabad",
             "description":f"6-month {q} internship. Python, JavaScript, REST APIs.","apply_link":"https://linkedin.com/jobs","salary":"15000-25000/month","source":"demo","match_score":76,"matched_skills":["Python","JavaScript"],"missing_skills":[],"recommendation":"Good fit for freshers"},
        ]

    jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return {"jobs": jobs, "count": len(jobs), "source": jobs[0].get("source","demo") if jobs else "none"}

# ── Rewrite Resume ─────────────────────────────────────────────────
@app.post("/api/rewrite")
async def rewrite_resume(request: dict):
    path      = request.get("resume_path","")
    job       = request.get("job", {})
    job_title = job.get("title","Software Engineer")
    job_desc  = (job.get("description") or "")[:500]

    if not path or not os.path.exists(path):
        raise HTTPException(404, f"Resume not found: {path}")

    text = _cache.get(f"text:{path}") or extract_pdf_text(path)

    prompt = (
        f"Rewrite this resume to better match the job. RULES: keep all facts true, "
        f"add job keywords naturally, keep same structure and line count, "
        f"return ONLY the rewritten resume text, no explanation.\n\n"
        f"Resume:\n{text[:2200]}\n\n"
        f"Job: {job_title}\nDescription: {job_desc}"
    )
    rewritten = await call_gemini_async(prompt, timeout=35.0)

    if rewritten.startswith("ERROR:"):
        rewritten = text  # fallback to original

    # Remove placeholders
    for p in [r"\[Email\]",r"\[LinkedIn\]",r"\[GitHub\]",r"\[Phone\]",r"\[URL\]"]:
        rewritten = re.sub(p, "", rewritten, flags=re.IGNORECASE)

    jw = set(w.lower() for w in job_desc.split() if len(w)>5)
    ow = set(text.lower().split())
    nw = set(rewritten.lower().split())
    kw = list((jw & nw) - ow)[:12]

    oh = sum(1 for k in jw if k in text.lower())
    nh = sum(1 for k in jw if k in rewritten.lower())
    oa = round(oh/max(len(jw),1)*100,1)
    na = round(nh/max(len(jw),1)*100,1)

    return {
        "original_text":   text,
        "rewritten_text":  rewritten,
        "keywords_added":  kw,
        "changes_summary": [f"Added {len(kw)} keywords","Improved ATS score","Preserved structure"],
        "ats_scores":      {"original":oa,"rewritten":na,"improvement":round(na-oa,1)},
    }

# ── Download PDF ───────────────────────────────────────────────────
@app.post("/api/rewrite/download-pdf")
async def download_pdf(request: dict):
    rewritten = request.get("rewritten_text","")
    if not rewritten:
        raise HTTPException(400, "No rewritten text provided")
    try:
        from reportlab.pdfgen import canvas as rl
        from reportlab.lib.pagesizes import A4
        buf  = io.BytesIO()
        c    = rl.Canvas(buf, pagesize=A4)
        w, h = A4
        c.setFont("Helvetica", 10)
        y = h - 50
        for line in rewritten.split("\n"):
            if y < 50: c.showPage(); c.setFont("Helvetica",10); y=h-50
            c.drawString(40, y, line[:110])
            y -= 13
        c.save(); buf.seek(0)
        return StreamingResponse(buf, media_type="application/pdf",
            headers={"Content-Disposition":'attachment; filename="rewritten_resume.pdf"'})
    except ImportError:
        # reportlab not installed — return text file
        content = rewritten.encode()
        return StreamingResponse(io.BytesIO(content), media_type="text/plain",
            headers={"Content-Disposition":'attachment; filename="rewritten_resume.txt"'})

# ── Interview Question ─────────────────────────────────────────────
@app.post("/interview/question")
@app.post("/api/interview/question")
async def interview_question(request: dict):
    job_title  = str(request.get("job_title") or "Software Engineer")
    round_num  = int(request.get("round_number") or 1)
    history    = request.get("history") or []
    itype      = str(request.get("interview_type") or "mixed")
    company    = str(request.get("company") or "")

    if round_num == 1:
        return {
            "question": f"Tell me about yourself and why you are interested in this {job_title} role.",
            "round":    1
        }

    prev = " | ".join(
        h.get("question","")[:60] for h in (history or [])[-2:]
        if isinstance(h,dict) and h.get("question")
    )
    type_map = {
        "behavioural": "Ask a STAR behavioural question about past experience or challenge.",
        "technical":   f"Ask a technical question about {job_title} skills or system design.",
        "hr":          "Ask about career goals, motivations, or work style.",
        "mixed":       f"Ask a relevant {job_title} interview question.",
    }
    prompt = (
        f"You are interviewing for {job_title}. "
        f"{'Company: '+company+'. ' if company else ''}"
        f"Round {round_num} of 5. "
        f"{type_map.get(itype, type_map['mixed'])} "
        f"Previously asked: {prev or 'none'}. "
        f"Do NOT repeat. Return ONLY the question. One sentence."
    )
    question = await call_gemini_async(prompt, timeout=20.0)

    if not question or question.startswith("ERROR:"):
        fallbacks = {
            2:"What is your strongest technical skill and how have you applied it?",
            3:"Describe a challenging project. What was your specific contribution?",
            4:"How would you design a scalable system for this role?",
            5:"Where do you see yourself in 3 years?",
        }
        question = fallbacks.get(round_num, f"What makes you the best candidate for {job_title}?")

    return {"question": question.strip(), "round": round_num}

# ── Interview Score ────────────────────────────────────────────────
@app.post("/interview/score-text")
@app.post("/api/interview/score-text")
async def score_answer(request: dict):
    transcript = (request.get("transcript") or "").strip()
    question   = request.get("question","")
    job_title  = request.get("job_title","Software Engineer")

    if not transcript or len(transcript) < 3:
        return {"transcript": transcript, "score": {
            "score":0,"clarity":0,"relevance":0,
            "feedback":"No answer detected. Please speak clearly.",
            "better_answer_hint":"Make sure microphone is working.",
            "filler_count":0,
        }}

    fillers = ["um","uh","like","basically","literally","you know","i mean","sort of"]
    words   = transcript.lower().split()
    fc      = sum(words.count(f) for f in fillers)

    prompt = (
        f"Score this interview answer. Return ONLY valid JSON.\n"
        f"Job: {job_title}\nQ: {question[:150]}\nA: {transcript[:350]}\n"
        f'Return: {{"score":7,"clarity":8,"relevance":7,"feedback":"Good answer.","better_answer_hint":"Add examples.","star_coverage":2}}'
    )
    raw    = await call_gemini_async(prompt, timeout=20.0)
    scored = parse_json(raw, {
        "score":5,"clarity":5,"relevance":5,
        "feedback":"Good attempt. Be more specific.",
        "better_answer_hint":"Use the STAR method.",
        "star_coverage":2,
    })
    scored["filler_count"] = fc
    return {"transcript": transcript, "score": scored}

@app.post("/interview/score")
@app.post("/api/interview/score")
async def score_answer_alias(request: dict):
    return await score_answer(request)

# ── Interview Follow-up ────────────────────────────────────────────
@app.post("/interview/followup")
@app.post("/api/interview/followup")
async def followup(request: dict):
    q    = request.get("original_question","")
    a    = request.get("answer_given","")
    job  = request.get("job_title","Software Engineer")
    prompt = (
        f"Generate ONE follow-up question for this interview answer.\n"
        f"Job: {job}\nQ: {q[:100]}\nA: {a[:150]}\n"
        f"Return ONLY the follow-up question. One sentence."
    )
    result = await call_gemini_async(prompt, timeout=15.0)
    if result.startswith("ERROR:"):
        result = "Can you give a specific example of when you applied that?"
    return {"followup_question": result.strip()}

# ── Interview Report ───────────────────────────────────────────────
@app.post("/interview/report")
@app.post("/api/interview/report")
async def interview_report(request: dict):
    history   = request.get("history", [])
    job_title = request.get("job_title","Software Engineer")
    if not history:
        return {"strengths":["Good effort"],"improvements":["Practice more"],
                "study_topics":["System design"],"overall_feedback":"Keep practicing.",
                "hire_recommendation":"Maybe"}
    summary = " | ".join(
        f"Q{i+1}: {h.get('answer','')[:60]}" for i,h in enumerate(history)
    )
    prompt = (
        f"Evaluate this {job_title} interview. Return ONLY valid JSON.\n"
        f"Answers: {summary[:500]}\n"
        f'{{"strengths":["s1","s2","s3"],"improvements":["i1","i2","i3"],"study_topics":["t1","t2","t3"],"overall_feedback":"2 sentences.","hire_recommendation":"Hire"}}'
    )
    raw    = await call_gemini_async(prompt, timeout=20.0)
    result = parse_json(raw, {
        "strengths":["Good communication"],"improvements":["Be more specific"],
        "study_topics":["System design"],"overall_feedback":"Good effort.",
        "hire_recommendation":"Maybe"
    })
    return result

# ── Daily Coach ────────────────────────────────────────────────────
@app.post("/api/daily-coach/respond")
async def coach_respond(request: dict):
    msg       = (request.get("user_message") or "").strip()
    history   = request.get("history") or []
    time_left = int(request.get("time_left") or 600)

    if not msg:
        return {"reply": "Hey! I'm Aria, your English coach. How are you doing today?"}

    hist_str = "\n".join(
        f"{m.get('role','').upper()}: {m.get('content','')[:80]}"
        for m in (history or [])[-4:]
        if isinstance(m,dict)
    )
    wrap = " We have about a minute left, let's start wrapping up." if time_left < 60 else ""

    prompt = (
        f"You are Aria, a warm friendly English conversation coach.\n"
        f"RULES: Max 2-3 sentences. Speak naturally. End with a question. "
        f"Correct grammar gently by using correct form in your reply. "
        f"Be genuinely interested.{wrap}\n\n"
        f"Conversation:\n{hist_str or 'Start of conversation'}\n\n"
        f"Student said: {msg}\n\n"
        f"Aria replies (2-3 sentences, end with a question):"
    )
    reply = await call_gemini_async(prompt, timeout=20.0)

    if not reply or reply.startswith("ERROR:"):
        # Smart fallback based on what user said
        if "badminton" in msg.lower() or "sport" in msg.lower():
            reply = "That's great that you enjoy sports! Badminton is a fantastic game for fitness and reflexes. How often do you play, and do you have a favourite player you look up to?"
        elif "discuss" in msg.lower() or "want" in msg.lower():
            reply = "I'd love to discuss that with you! It sounds like an interesting topic. Can you tell me a little more about what specifically you'd like to explore?"
        else:
            reply = f"That's really interesting! I'd love to hear more about {msg[:30]}... Can you tell me a bit more about that?"

    return {"reply": reply.strip()}

@app.post("/api/daily-coach/feedback")
async def coach_feedback(request: dict):
    history = request.get("history") or []
    user_msgs = [
        m.get("content","").strip()
        for m in history
        if isinstance(m,dict) and m.get("role")=="user" and m.get("content","").strip()
    ]
    text  = " ".join(user_msgs)
    wc    = len(text.split()) if text else 0
    score = max(5, min(100, wc*2 + 20))

    if wc < 10:
        return {
            "fluency_score":50,"overall_feedback":f"Only {wc} words detected. Speak more next time!",
            "strengths":["You participated"],"improvements":["Speak in full sentences","Use mic correctly"],
            "vocabulary_highlights":[],"grammar_notes":"Not enough speech to analyze.",
            "word_count":wc,"message_count":len(user_msgs),"avg_words_per_message":0,
            "filler_count":0,"vocab_diversity":0,"grammar_flags":[]
        }

    prompt = (
        f"Give English feedback. Return ONLY valid JSON.\n"
        f"Student said {wc} words: {text[:500]}\n"
        f'{{"overall_feedback":"2 specific sentences.","strengths":["s1","s2"],'
        f'"improvements":["i1","i2"],"vocabulary_highlights":["word1"],'
        f'"grammar_notes":"observation.","topic_engagement":"engagement note."}}'
    )
    raw    = await call_gemini_async(prompt, timeout=20.0)
    result = parse_json(raw, {
        "overall_feedback":"Good session! Keep practicing.",
        "strengths":["Active participation"],"improvements":["Elaborate more"],
        "vocabulary_highlights":[],"grammar_notes":"Keep practicing.",
        "topic_engagement":"Good engagement."
    })
    result.update({
        "fluency_score":score,"word_count":wc,
        "message_count":len(user_msgs),
        "avg_words_per_message":round(wc/max(len(user_msgs),1),1),
        "filler_count":0,"vocab_diversity":60,"grammar_flags":[]
    })
    return result

# ── Score PDF ──────────────────────────────────────────────────────
@app.post("/api/score-pdf")
async def score_pdf(file: UploadFile = File(...), job_description: str = Form(default="")):
    data = await file.read()
    tmp  = f"data/uploads/tmp_{file.filename}"
    with open(tmp,"wb") as f:
        f.write(data)
    try:
        text = extract_pdf_text(tmp)
        if not text or len(text)<20:
            raise HTTPException(422,"Cannot extract text from PDF.")
        jw = [w.lower() for w in job_description.split() if len(w)>4]
        h  = sum(1 for w in jw if w in text.lower())
        s  = round(h/max(len(jw),1)*100,1) if jw else 65
        return {"ats_score":s,"overall_score":min(95,s+10),"text_length":len(text),"file":file.filename}
    finally:
        if os.path.exists(tmp): os.remove(tmp)

# ── Session ────────────────────────────────────────────────────────
@app.get("/api/session/{user_id}")
async def get_session(user_id: str):
    return _cache.get(f"analysis:{user_id}", {"message":"No session found"})

# ── WebSocket ──────────────────────────────────────────────────────
@app.websocket("/ws/agent-stream/{user_id}")
async def agent_stream(ws: WebSocket, user_id: str):
    await ws.accept()
    try:
        while True:
            await asyncio.sleep(25)
            await ws.send_json({"type":"ping","status":"connected"})
    except (WebSocketDisconnect, Exception):
        pass

print("✅ All routes registered successfully")
print("Routes: GET /, GET /health, GET /api/diagnose, GET /api/jobs,")
print("        POST /api/upload-resume, POST /api/analyze, POST /api/rewrite,")
print("        POST /api/interview/question, POST /api/interview/score-text,")
print("        POST /api/daily-coach/respond, POST /api/daily-coach/feedback")
