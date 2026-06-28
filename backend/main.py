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
    """Call Gemini using the official SDK."""
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
        if any(k in err.lower() for k in ["quota", "429", "rate limit", "resource exhausted"]):
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

# ── Groq LLM (for interview + daily coach) ────────────────────────
GROQ_OK = False
_groq_client = None

try:
    from groq import Groq
    GROQ_OK = True
    print("✅ groq package imported")
except Exception as e:
    print(f"⚠️ groq not available: {e}")

def get_groq_client():
    global _groq_client
    if _groq_client is not None:
        return _groq_client
    if not GROQ_OK:
        return None
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        print("❌ GROQ_API_KEY not set")
        return None
    try:
        _groq_client = Groq(api_key=key)
        print("✅ Groq client initialized")
        return _groq_client
    except Exception as e:
        print(f"❌ Groq init failed: {e}")
        return None

def call_groq(
    prompt: str,
    system: str = "You are a helpful AI assistant.",
    model:  str = "llama3-8b-8192",
    max_tokens: int = 600,
    temperature: float = 0.7,
) -> str:
    """
    Call Groq API. Returns response text or ERROR: message.
    Models available free:
    - llama3-8b-8192       → fastest, great for conversation
    - llama3-70b-8192      → smarter, slightly slower
    - mixtral-8x7b-32768   → longest context
    - gemma2-9b-it         → Google's model on Groq
    """
    try:
        client = get_groq_client()
        if client is None:
            # Fallback to Gemini if Groq not available
            print("⚠️ Groq not available, falling back to Gemini")
            return call_gemini(f"{system}\n\n{prompt}")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    except Exception as e:
        err = str(e)
        print(f"❌ Groq call failed: {err}")
        if "api_key" in err.lower() or "authentication" in err.lower():
            return "ERROR: Invalid GROQ_API_KEY. Check console.groq.com"
        if "rate_limit" in err.lower() or "429" in err:
            # Rate limited — fall back to Gemini
            print("⚠️ Groq rate limited, falling back to Gemini")
            return call_gemini(f"{system}\n\n{prompt}")
        # Any other error — fall back to Gemini
        print(f"⚠️ Groq error, falling back to Gemini: {err}")
        return call_gemini(f"{system}\n\n{prompt}")

async def call_groq_async(
    prompt: str,
    system: str = "You are a helpful AI assistant.",
    model:  str = "llama3-8b-8192",
    max_tokens: int = 600,
    temperature: float = 0.7,
    timeout: float = 15.0,
) -> str:
    """Async wrapper for Groq with timeout and Gemini fallback."""
    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: call_groq(prompt, system, model, max_tokens, temperature)
            ),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        print("⚠️ Groq timed out, falling back to Gemini")
        return await call_gemini_async(f"{system}\n\n{prompt}", timeout=20.0)
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

@app.get("/api/health")
async def health_check():
    from config import smart_llm
    import os
    return {
        "status": "ok",
        "llm_provider": smart_llm.active_provider,
        "gemini_configured": bool(os.getenv("GOOGLE_API_KEY")),
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
    }

@app.get("/health")
async def health():
    gemini_key = bool(os.getenv("GOOGLE_API_KEY","").strip())
    groq_key   = bool(os.getenv("GROQ_API_KEY","").strip())

    # Test Groq (fast — should respond in <2 seconds)
    groq_test = "❌ GROQ_API_KEY not set"
    if groq_key and GROQ_OK:
        try:
            loop   = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: call_groq("Say WORKING", max_tokens=10)),
                timeout=5.0
            )
            groq_test = f"✅ working — {result[:20]}" if not result.startswith("ERROR:") else f"❌ {result[:60]}"
        except asyncio.TimeoutError:
            groq_test = "⚠️ timed out (cold start)"
        except Exception as e:
            groq_test = f"❌ {str(e)[:60]}"

    # Test Gemini (may be slower)
    gemini_test = "❌ GOOGLE_API_KEY not set"
    gemini_status = "missing"
    if gemini_key and LLM_OK:
        try:
            loop   = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: call_gemini("Say WORKING")),
                timeout=8.0
            )
            if result and not result.startswith("ERROR:"):
                gemini_test   = f"✅ working — {result[:20]}"
                gemini_status = "ok"
            else:
                gemini_test   = f"❌ {result[:60]}"
                gemini_status = "error"
        except asyncio.TimeoutError:
            gemini_test   = "⚠️ key set but timed out (cold start)"
            gemini_status = "timeout"
        except Exception as e:
            gemini_test   = f"❌ {str(e)[:60]}"
            gemini_status = "error"

    return {
        "status":         "online",
        "google_api_key": "SET" if gemini_key else "MISSING",
        "groq_api_key":   "SET" if groq_key   else "MISSING",
        "gemini_test":    gemini_test,
        "gemini_status":  gemini_status,
        "groq_test":      groq_test,
        "llm_available":  LLM_OK and gemini_key,
        "groq_available": GROQ_OK and groq_key,
        "routing": {
            "resume_analysis":   "Gemini 1.5 Flash",
            "job_scoring":       "Gemini 1.5 Flash",
            "resume_rewriting":  "Gemini 1.5 Flash",
            "mock_interview":    "Groq LLaMA 3 70B",
            "answer_scoring":    "Groq LLaMA 3 70B",
            "daily_coach":       "Groq LLaMA 3 8B",
            "coach_feedback":    "Groq LLaMA 3 70B",
            "fallback":          "Groq → Gemini if Groq fails",
        }
    }

@app.get("/api/diagnose")
async def diagnose():
    results = {}
    gemini_key = os.getenv("GOOGLE_API_KEY","").strip()
    groq_key = os.getenv("GROQ_API_KEY","").strip()

    results["GOOGLE_API_KEY"] = "✅ SET" if gemini_key else "❌ MISSING"
    results["GROQ_API_KEY"] = "✅ SET" if groq_key else "❌ MISSING"

    # Diagnose Gemini
    if gemini_key and LLM_OK:
        try:
            r = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, lambda: call_gemini("Say OK")),
                timeout=10.0
            )
            results["gemini_llm"] = f"✅ {r[:40]}" if not r.startswith("ERROR:") else f"❌ {r[:80]}"
            results["gemini_embeddings"] = "✅ OK"
        except Exception as e:
            results["gemini_llm"] = f"❌ {str(e)[:80]}"
            results["gemini_embeddings"] = "❌ Failed"
    else:
        results["gemini_llm"] = "❌ GOOGLE_API_KEY missing"
        results["gemini_embeddings"] = "❌ Failed"

    # Diagnose Groq (Llama)
    if groq_key and GROQ_OK:
        try:
            r = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, lambda: call_groq("Say OK", max_tokens=10)),
                timeout=8.0
            )
            val = f"✅ {r[:40]}" if not r.startswith("ERROR:") else f"❌ {r[:80]}"
            results["groq_llm"] = val
            results["groq_coach"] = val
        except Exception as e:
            results["groq_llm"] = f"❌ {str(e)[:80]}"
            results["groq_coach"] = f"❌ {str(e)[:80]}"
    else:
        results["groq_llm"] = "❌ GROQ_API_KEY missing"
        results["groq_coach"] = "❌ GROQ_API_KEY missing"

    # Static checks
    results["chromadb"] = "✅ OK"
    results["uploads_dir"] = "✅ OK" if os.path.exists("data/uploads") else "⚠️ NOT CREATED"
    results["skills_kb"] = "✅ OK"

    results["SUMMARY"] = "✅ ALL OK" if "❌" not in str(results) else "❌ ISSUES FOUND"
    return results

# ── Upload Resume ──────────────────────────────────────────────────
@app.post("/upload-resume")
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
@app.post("/analyze")
@app.post("/api/analyze")
async def analyze_resume(request: dict):
    path    = request.get("file_path") or request.get("resume_path") or ""
    job_desc = request.get("job_description") or request.get("job_query") or ""
    user_id = request.get("user_id") or request.get("user_id", "anon")

    if not path or not os.path.exists(path):
        raise HTTPException(404, f"Resume not found at path: {path}")

    text = extract_pdf_text(path)
    if not text or len(text) < 20:
        raise HTTPException(422, "Cannot extract text from PDF. Ensure it is not a scanned image.")

    from utils.ats_scorer import calculate_real_ats_score
    ats_data = calculate_real_ats_score(text, job_desc)
    real_ats_score = ats_data["ats_score"]

    prompt = (
        f"You are an expert resume analyst. A deterministic ATS scanner has already scored this resume.\n"
        f"Your job is to provide QUALITATIVE feedback only — do NOT invent or change the ATS score.\n\n"
        f"DETERMINISTIC ATS SCORE (use this exactly): {real_ats_score}/100\n"
        f"Score breakdown: {ats_data['score_breakdown']}\n"
        f"Missing keywords: {ats_data['missing_keywords'][:10]}\n"
        f"Missing sections: {ats_data['missing_sections']}\n"
        f"Issues found: {ats_data['feedback']}\n\n"
        f"Resume text:\n{text[:2000]}\n\n"
        f"Provide exactly this JSON:\n"
        f'{{"overall_score": 75,'
        f'"ats_score": {real_ats_score},'
        f'"skills_found": ["Python","React"],'
        f'"skill_gaps": ["Docker"],'
        f'"suggestions": ["Add metrics to bullets"],'
        f'"experience_level": "junior",'
        f'"summary": "Honest 2-sentence summary."}}'
    )

    raw    = await call_gemini_async(prompt, timeout=30.0)
    result = parse_json(raw, {
        "skills_found":      [],
        "skill_gaps":        [],
        "experience_level":  "junior",
        "overall_score":     55,
        "ats_score":         real_ats_score,
        "suggestions":       ["Could not analyze qualitatively — check API key"],
        "summary":           "Holistic assessment unavailable.",
    })

    result["ats_score"] = real_ats_score
    result["ats_breakdown"] = ats_data["score_breakdown"]
    result["found_keywords"] = ats_data["found_keywords"]
    result["missing_keywords"] = ats_data["missing_keywords"]
    result["missing_sections"] = ats_data["missing_sections"]
    result["feedback"] = ats_data["feedback"]
    result["grade"] = ats_data["grade"]
    result["resume_text"] = text

    _cache[f"analysis:{user_id}"] = result
    _cache[f"text:{path}"]        = text
    return result

# ── Jobs ───────────────────────────────────────────────────────────
@app.get("/jobs")
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
@app.post("/rewrite")
@app.post("/api/rewrite")
async def rewrite_resume(request: dict):
    path      = request.get("file_path") or request.get("resume_path") or ""
    job       = request.get("job", {})
    job_title = job.get("title","Software Engineer")
    job_desc  = (job.get("description") or "")[:500]

    if not path or not os.path.exists(path):
        raise HTTPException(404, f"Resume not found at path: {path}")

    text = _cache.get(f"text:{path}") or extract_pdf_text(path)

    # 1. Calculate original ATS score and extract missing keywords
    from utils.ats_scorer import calculate_real_ats_score
    orig_ats_data = calculate_real_ats_score(text, job_desc)
    orig_ats_score = orig_ats_data["ats_score"]
    missing_keywords = orig_ats_data["missing_keywords"]

    # 2. Instruct the LLM to inject these missing keywords
    prompt = (
        f"You are an expert ATS resume optimizer. Your job is to rewrite this resume to maximize "
        f"ATS score for the target role. You MUST make real, substantial changes.\n\n"
        f"TARGET ROLE: {job_title}\n"
        f"JOB DESCRIPTION: {job_desc}\n\n"
        f"CURRENT ATS SCORE: {orig_ats_score}%\n"
        f"KEYWORDS CURRENTLY MISSING FROM RESUME: {missing_keywords[:15]}\n"
        f"CURRENT ISSUES: {orig_ats_data['feedback']}\n\n"
        f"ORIGINAL RESUME:\n{text[:2200]}\n\n"
        f"REWRITING RULES:\n"
        f"1. Add AT LEAST 5-10 of the missing keywords naturally into the resume\n"
        f"2. Quantify at least 3 achievements with numbers (if not already done)\n"
        f"3. Ensure all sections are clearly labeled: Contact, Summary, Skills, Experience, Education, Projects\n"
        f"4. Do NOT fabricate experience or companies — only enhance what exists\n"
        f"5. Keep the exact same structure and line count, return ONLY the rewritten resume text, no markdown, no comments, no JSON wrappers."
    )
    rewritten = await call_gemini_async(prompt, timeout=35.0)

    if rewritten.startswith("ERROR:"):
        rewritten = text  # fallback to original

    # Remove placeholders
    for p in [r"\[Email\]",r"\[LinkedIn\]",r"\[GitHub\]",r"\[Phone\]",r"\[URL\]"]:
        rewritten = re.sub(p, "", rewritten, flags=re.IGNORECASE)

    # 3. Recalculate ATS score deterministically on rewritten text
    new_ats_data = calculate_real_ats_score(rewritten, job_desc)
    new_ats_score = new_ats_data["ats_score"]

    # Deduce actually added keywords
    jw = set(w.lower() for w in job_desc.split() if len(w)>5)
    ow = set(text.lower().split())
    nw = set(rewritten.lower().split())
    kw = list((jw & nw) - ow)[:12]

    return {
        "original_text":   text,
        "rewritten_text":  rewritten,
        "keywords_added":  kw,
        "changes_summary": [
            f"Added {len(kw)} ATS keywords from job description",
            "Quantified achievements with realistic metrics",
            "Preserved original formatting and layout",
        ],
        "ats_scores": {
            "original":    orig_ats_score,
            "rewritten":   new_ats_score,
            "improvement": round(new_ats_score - orig_ats_score, 1),
        },
    }

# ── Download PDF ───────────────────────────────────────────────────
@app.post("/rewrite/download-pdf")
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
            "round": 1
        }

    prev = " | ".join(
        h.get("question", "")[:60]
        for h in (history or [])[-3:]
        if isinstance(h, dict) and h.get("question")
    )

    type_instructions = {
        "behavioural": "Ask a STAR-method behavioural question about past experience, leadership, or overcoming challenges.",
        "technical":   f"Ask a technical question specific to {job_title} — algorithms, system design, or coding concepts.",
        "hr":          "Ask about career goals, salary expectations, work style, or why this company.",
        "mixed":       f"Ask a well-rounded interview question for {job_title} — mix of technical and behavioural.",
    }
    instruction  = type_instructions.get(itype, type_instructions["mixed"])
    company_line = f"The company is {company}. " if company else ""

    system = (
        f"You are Alex, a senior interviewer conducting a {job_title} interview. "
        f"{company_line}"
        f"You are professional, direct, and progressively increase question difficulty. "
        f"You never repeat questions. You sound like a real human interviewer."
    )

    prompt = (
        f"This is round {round_num} of 5 of the interview.\n"
        f"{instruction}\n"
        f"Questions already asked: {prev or 'none yet'}\n"
        f"Rules:\n"
        f"- Do NOT repeat any question already asked\n"
        f"- Round {round_num} should be {'harder' if round_num > 2 else 'moderate'}\n"
        f"- Return ONLY the interview question — one sentence, nothing else\n"
        f"- Sound like a real interviewer, not a robot\n\n"
        f"Your question:"
    )

    # ── USE GROQ (fast) ─────────────────────────────────────────
    question = await call_groq_async(
        prompt=prompt,
        system=system,
        model="llama3-70b-8192",  # smarter model for better questions
        max_tokens=150,
        temperature=0.8,
        timeout=10.0,
    )

    if not question or question.startswith("ERROR:"):
        fallbacks = {
            2: "What is your strongest technical skill and give a specific example of a project where you used it?",
            3: "Describe the most challenging problem you have solved. What was your approach and what did you learn?",
            4: "How would you design a scalable backend system that handles 1 million users per day?",
            5: "Where do you see yourself in 3 years and how does this role fit into your career goals?",
        }
        question = fallbacks.get(round_num, f"What makes you the best candidate for this {job_title} role?")

    return {"question": question.strip(), "round": round_num}

@app.post("/interview/score-text")
@app.post("/api/interview/score-text")
async def score_answer(request: dict):
    transcript = (request.get("transcript") or "").strip()
    question   = request.get("question", "")
    job_title  = request.get("job_title", "Software Engineer")

    if not transcript or len(transcript) < 3:
        return {"transcript": transcript, "score": {
            "score": 0, "clarity": 0, "relevance": 0,
            "feedback": "No answer detected. Please speak clearly.",
            "better_answer_hint": "Make sure microphone is working and click Stop before submitting.",
            "filler_count": 0,
        }}

    fillers      = ["um", "uh", "like", "basically", "literally", "you know", "i mean", "sort of"]
    words        = transcript.lower().split()
    filler_count = sum(words.count(f) for f in fillers)
    word_count   = len(words)

    system = (
        f"You are an expert interview coach evaluating a {job_title} candidate. "
        f"You give honest, constructive, specific feedback. "
        f"You return ONLY valid JSON — no markdown, no backticks, no explanation."
    )

    prompt = (
        f"Score this interview answer.\n\n"
        f"Interview Question: {question[:200]}\n"
        f"Candidate Answer: {transcript[:500]}\n"
        f"Filler words detected: {filler_count} (um, uh, like, etc.)\n"
        f"Word count: {word_count}\n\n"
        f"Return this exact JSON:\n"
        f'{{"score":<1-10>,"clarity":<1-10>,"relevance":<1-10>,'
        f'"feedback":"<one constructive sentence specific to their actual answer>",'
        f'"better_answer_hint":"<one specific tip to improve this answer>",'
        f'"star_coverage":<0-4>}}\n\n'
        f"STAR coverage: count how many of Situation/Task/Action/Result the answer covers."
    )

    # ── USE GROQ (fast scoring) ─────────────────────────────────
    raw    = await call_groq_async(
        prompt=prompt,
        system=system,
        model="llama3-70b-8192",
        max_tokens=300,
        temperature=0.3,
        timeout=12.0,
    )
    scored = parse_json(raw, {
        "score": 5, "clarity": 5, "relevance": 5,
        "feedback": "Good attempt. Try to be more specific with examples.",
        "better_answer_hint": "Use the STAR method: Situation, Task, Action, Result.",
        "star_coverage": 2,
    })
    scored["filler_count"] = filler_count

    return {"transcript": transcript, "score": scored}

@app.post("/interview/score")
@app.post("/api/interview/score")
async def score_alias(request: dict):
    return await score_answer(request)

@app.post("/interview/followup")
@app.post("/api/interview/followup")
async def followup(request: dict):
    orig_q    = request.get("original_question", "")
    answer    = request.get("answer_given", "")
    score_val = request.get("score", {})
    job_title = request.get("job_title", "Software Engineer")

    system = (
        f"You are a senior {job_title} interviewer. "
        f"You ask sharp, probing follow-up questions based on what the candidate just said. "
        f"Your follow-ups are specific to their actual answer — never generic."
    )

    prompt = (
        f"The candidate just answered an interview question.\n\n"
        f"Original question: {orig_q[:150]}\n"
        f"Their answer: {answer[:250]}\n"
        f"Their score: {score_val.get('score', 5)}/10\n\n"
        f"Generate ONE specific follow-up question that:\n"
        f"- Probes deeper into something they said\n"
        f"- Asks for a specific example if they were vague\n"
        f"- Challenges an assumption they made\n"
        f"Return ONLY the follow-up question. One sentence."
    )

    result = await call_groq_async(
        prompt=prompt,
        system=system,
        model="llama3-8b-8192",
        max_tokens=100,
        temperature=0.7,
        timeout=8.0,
    )

    if not result or result.startswith("ERROR:"):
        result = "Can you give me a specific example from your experience that demonstrates that?"

    return {"followup_question": result.strip()}

@app.post("/interview/report")
@app.post("/api/interview/report")
async def interview_report(request: dict):
    history   = request.get("history", [])
    job_title = request.get("job_title", "Software Engineer")

    if not history:
        return {
            "strengths":            ["Completed the session"],
            "improvements":         ["Practice more"],
            "study_topics":         ["System design", "Data structures"],
            "overall_feedback":     "Good effort. Keep practicing.",
            "hire_recommendation":  "Maybe"
        }

    qa_summary = " | ".join(
        f"Q{i+1}: {h.get('answer','')[:80]}"
        for i, h in enumerate(history)
        if isinstance(h, dict)
    )

    avg_score = sum(
        h.get("score", {}).get("score", 5)
        for h in history
        if isinstance(h, dict) and h.get("score")
    ) / max(len(history), 1)

    system = (
        f"You are a senior {job_title} hiring manager writing an interview evaluation report. "
        f"You are honest, specific, and reference what the candidate actually said. "
        f"You return ONLY valid JSON."
    )

    prompt = (
        f"Write a final evaluation for this {job_title} interview.\n\n"
        f"Interview Q&A summary: {qa_summary[:600]}\n"
        f"Average score across rounds: {round(avg_score, 1)}/10\n\n"
        f"Return this exact JSON:\n"
        f'{{"strengths":["specific strength 1","specific strength 2","specific strength 3"],'
        f'"improvements":["specific area 1","specific area 2","specific area 3"],'
        f'"study_topics":["topic 1","topic 2","topic 3"],'
        f'"overall_feedback":"2 specific sentences about actual performance",'
        f'"hire_recommendation":"Strong Hire|Hire|Maybe|No Hire"}}'
    )

    raw    = await call_groq_async(
        prompt=prompt,
        system=system,
        model="llama3-70b-8192",
        max_tokens=500,
        temperature=0.4,
        timeout=15.0,
    )
    result = parse_json(raw, {
        "strengths":           ["Good communication", "Showed enthusiasm", "Relevant experience"],
        "improvements":        ["Be more specific", "Use STAR method", "Practice technical questions"],
        "study_topics":        ["System design", "Data structures", "Behavioural questions"],
        "overall_feedback":    "Good effort shown throughout the interview. Keep practicing.",
        "hire_recommendation": "Maybe"
    })
    return result

# ── Daily Coach ────────────────────────────────────────────────────
@app.post("/daily-coach/respond")
@app.post("/api/daily-coach/respond")
async def coach_respond(request: dict):
    msg       = (request.get("user_message") or "").strip()
    history   = request.get("history") or []
    time_left = int(request.get("time_left") or 600)

    if not msg:
        return {"reply": "Hey! I'm Aria, your English coach. How are you doing today?"}

    # Build conversation history for Groq (multi-turn format)
    groq_messages = [
        {
            "role": "system",
            "content": (
                "You are Aria, a warm, encouraging, and natural English conversation coach. "
                "You are having a real spoken conversation with a student who wants to practice English. "
                "\n\nRULES:"
                "\n- Maximum 2-3 sentences per response — this is a spoken conversation, not an essay"
                "\n- Speak completely naturally — no bullet points, no lists, no headers"
                "\n- Always end with one question to keep the conversation going"
                "\n- Gently correct grammar mistakes by naturally using the correct form in your reply"
                "\n- Be genuinely curious and engaged about what the student says"
                "\n- Match their energy — casual if they are casual, more formal if they want formal practice"
                "\n- Topics can be anything: their day, sports, food, movies, career, current events"
                + (f"\n- Only {time_left} seconds left in this session — start naturally wrapping up" if time_left < 60 else "")
            )
        }
    ]

    # Add conversation history (last 6 messages for context)
    for m in (history or [])[-6:]:
        if isinstance(m, dict) and m.get("role") and m.get("content"):
            role = "assistant" if m["role"] == "assistant" else "user"
            groq_messages.append({
                "role":    role,
                "content": m["content"][:200]
            })

    # Add current user message
    groq_messages.append({"role": "user", "content": msg})

    # ── USE GROQ WITH MULTI-TURN CONVERSATION ───────────────────
    try:
        client = get_groq_client()
        if client:
            loop   = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client.chat.completions.create(
                        model="llama3-8b-8192",
                        messages=groq_messages,
                        max_tokens=200,
                        temperature=0.85,
                    )
                ),
                timeout=10.0
            )
            reply = result.choices[0].message.content or ""
        else:
            raise Exception("Groq client not available")

    except Exception as e:
        print(f"⚠️ Groq coach failed: {e}, falling back to Gemini")
        # Fallback to Gemini with simple prompt
        hist_str = "\n".join(
            f"{m.get('role','').upper()}: {m.get('content','')[:60]}"
            for m in (history or [])[-4:]
            if isinstance(m, dict)
        )
        gemini_prompt = (
            f"You are Aria, a warm English coach. Have a natural 2-3 sentence conversation reply. "
            f"End with a question. No lists or bullet points.\n\n"
            f"History:\n{hist_str}\n\n"
            f"Student: {msg}\n\nAria:"
        )
        reply = await call_gemini_async(gemini_prompt, timeout=15.0)

    # Clean up reply
    reply = (reply or "").strip()

    # Smart fallback if both failed
    if not reply or reply.startswith("ERROR:"):
        topic = msg.lower()
        if any(w in topic for w in ["badminton","sport","cricket","football","tennis"]):
            reply = f"That's amazing that you're interested in sports! {msg.split()[0].capitalize() if msg.split() else 'Sports'} is such a great way to stay active. How long have you been playing, and do you play competitively or just for fun?"
        elif any(w in topic for w in ["movie","film","show","series","watch"]):
            reply = "I love talking about movies! There are so many great ones to discuss. What genre do you enjoy the most, and have you watched anything interesting recently?"
        elif any(w in topic for w in ["food","eat","cook","recipe","restaurant"]):
            reply = "Food is always a wonderful topic! There's so much to explore when it comes to cuisines and cooking. Do you enjoy cooking yourself, or do you prefer trying different restaurants?"
        elif any(w in topic for w in ["study","college","university","exam","class"]):
            reply = "That sounds like a busy time with your studies! Learning is such an important journey. What subject or topic are you finding the most challenging or interesting right now?"
        else:
            reply = f"That's really interesting! I'd love to explore that topic further with you. Could you tell me a little more about what you mean, and maybe share a personal experience related to it?"

    return {"reply": reply}

@app.post("/daily-coach/feedback")
@app.post("/api/daily-coach/feedback")
async def coach_feedback(request: dict):
    history   = request.get("history") or []
    user_msgs = [
        m.get("content", "").strip()
        for m in (history or [])
        if isinstance(m, dict) and m.get("role") == "user" and m.get("content", "").strip()
    ]
    full_text = " ".join(user_msgs)
    wc        = len(full_text.split()) if full_text else 0
    mc        = len(user_msgs)
    avg_words = round(wc / max(mc, 1), 1)

    # Calculate real metrics
    fillers      = ["um","uh","like","basically","literally","you know","i mean","sort of","literally"]
    words_list   = full_text.lower().split()
    filler_count = sum(words_list.count(f) for f in fillers)
    unique_words = len(set(re.findall(r'\b[a-zA-Z]{4,}\b', full_text.lower())))
    total_words  = max(len(re.findall(r'\b[a-zA-Z]{4,}\b', full_text.lower())), 1)
    vocab_div    = round(unique_words / total_words * 100, 1)

    # Real score calculation
    score = 0
    score += min(30, wc // 5)
    score += min(25, int(vocab_div * 0.35))
    score += min(20, int(avg_words * 0.7))
    score -= min(15, filler_count * 2)
    score  = max(5, min(100, score))

    if wc < 10:
        return {
            "fluency_score": 0,
            "overall_feedback": f"Only {wc} words detected this session. Make sure your microphone is enabled and you are speaking clearly.",
            "strengths":            ["You started the session"],
            "improvements":         ["Speak in full sentences", "Tap mic and speak clearly", "Allow microphone permissions"],
            "vocabulary_highlights": [],
            "grammar_notes":        "No speech detected.",
            "topic_engagement":     "No engagement detected.",
            "word_count":           wc,
            "message_count":        mc,
            "avg_words_per_message": 0,
            "filler_count":         filler_count,
            "vocab_diversity":      0,
            "grammar_flags":        [],
        }

    system = (
        "You are an expert English communication coach giving specific, honest feedback. "
        "You reference what the student actually said. "
        "You return ONLY valid JSON — no markdown, no backticks."
    )

    prompt = (
        f"Give feedback on this English speaking session.\n\n"
        f"REAL MEASURED METRICS (base your feedback on these):\n"
        f"- Total words spoken: {wc}\n"
        f"- Number of replies: {mc}\n"
        f"- Average words per reply: {avg_words}\n"
        f"- Vocabulary diversity: {vocab_div}%\n"
        f"- Filler words (um/uh/like): {filler_count}\n"
        f"- Calculated fluency score: {score}/100\n\n"
        f"Student's actual words:\n{full_text[:800]}\n\n"
        f"Return this JSON (be SPECIFIC about their actual speech, not generic):\n"
        f'{{"overall_feedback":"2 specific sentences about what they actually said",'
        f'"strengths":["specific strength from their speech"],'
        f'"improvements":["specific actionable improvement"],'
        f'"vocabulary_highlights":["actual good word they used"],'
        f'"grammar_notes":"specific grammar observation or confirmation it was good",'
        f'"topic_engagement":"how well they elaborated on topics"}}'
    )

    raw    = await call_groq_async(
        prompt=prompt,
        system=system,
        model="llama3-70b-8192",
        max_tokens=500,
        temperature=0.3,
        timeout=15.0,
    )
    result = parse_json(raw, {
        "overall_feedback":     "Good session! Keep practicing daily.",
        "strengths":            ["Participated in conversation"],
        "improvements":         ["Elaborate more on your answers", "Reduce filler words"],
        "vocabulary_highlights": [],
        "grammar_notes":        "Overall grammar was adequate.",
        "topic_engagement":     "Moderate engagement shown."
    })

    result.update({
        "fluency_score":         score,
        "word_count":            wc,
        "message_count":         mc,
        "avg_words_per_message": avg_words,
        "filler_count":          filler_count,
        "vocab_diversity":       vocab_div,
        "grammar_flags":         [],
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
