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
PDF_OK    = False
CHROMA_OK = False

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

# ── ADD GROQ AS THE ONLY LLM ──────────────────────────────────────
GROQ_OK     = False
_groq_client = None

try:
    from groq import Groq as GroqClient
    GROQ_OK = True
    print("✅ Groq package imported")
except Exception as e:
    print(f"❌ Groq import failed: {e} — run: pip install groq")

def get_groq():
    global _groq_client
    if _groq_client is not None:
        return _groq_client
    if not GROQ_OK:
        print("❌ Groq package not installed")
        return None
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        print("❌ GROQ_API_KEY not set in environment")
        return None
    try:
        _groq_client = GroqClient(api_key=key)
        print("✅ Groq client initialized")
        return _groq_client
    except Exception as e:
        print(f"❌ Groq init failed: {e}")
        return None

def call_groq(
    prompt:      str,
    system:      str   = "You are a helpful AI assistant. Be concise and accurate.",
    model:       str   = "llama-3.3-70b-versatile",
    max_tokens:  int   = 1000,
    temperature: float = 0.3,
) -> str:
    """
    Call Groq API synchronously.
    Returns response text or ERROR: message.
    Never throws — always returns a string.
    """
    client = get_groq()
    if client is None:
        return "ERROR: Groq not available. Set GROQ_API_KEY in Render environment variables."
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        result = response.choices[0].message.content or ""
        return result.strip()
    except Exception as e:
        err = str(e)
        print(f"❌ Groq call failed ({model}): {err[:100]}")
        if "rate_limit" in err.lower() or "429" in err:
            # Rate limited — try smaller model
            if model != "llama-3.1-8b-instant":
                print("⚠️ Rate limited on 70b, retrying with 8b")
                try:
                    response = client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user",   "content": prompt},
                        ],
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    return (response.choices[0].message.content or "").strip()
                except Exception as e2:
                    return f"ERROR: Rate limited. Wait 1 minute and try again."
            return "ERROR: Rate limited. Wait 1 minute and try again."
        if "api_key" in err.lower() or "auth" in err.lower():
            return "ERROR: Invalid GROQ_API_KEY. Check Render environment variables."
        return f"ERROR: {err[:100]}"

async def call_groq_async(
    prompt:      str,
    system:      str   = "You are a helpful AI assistant.",
    model:       str   = "llama-3.3-70b-versatile",
    max_tokens:  int   = 1000,
    temperature: float = 0.3,
    timeout:     float = 25.0,
) -> str:
    """Async wrapper for Groq. Never throws."""
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
        print(f"⚠️ Groq timed out after {timeout}s")
        return "ERROR: Request timed out. Please try again."
    except Exception as e:
        return f"ERROR: {str(e)[:100]}"

# Backwards compatibility aliases
call_gemini       = lambda p: call_groq(p)
call_gemini_async = lambda p, timeout=25.0: call_groq_async(p, timeout=timeout)

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
    groq_key = bool(os.getenv("GROQ_API_KEY", "").strip())
    groq_test = "❌ GROQ_API_KEY not set in Render Environment"
    groq_status = "missing"

    if groq_key and GROQ_OK:
        try:
            loop   = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: call_groq("Say WORKING", max_tokens=5, model="llama-3.1-8b-instant")
                ),
                timeout=8.0
            )
            if result and not result.startswith("ERROR:"):
                groq_test   = f"✅ working — {result[:20]}"
                groq_status = "ok"
            else:
                groq_test   = f"❌ {result[:80]}"
                groq_status = "error"
        except asyncio.TimeoutError:
            groq_test   = "⚠️ key set but timed out (cold start)"
            groq_status = "timeout"
        except Exception as e:
            groq_test   = f"❌ {str(e)[:80]}"
            groq_status = "error"

    return {
        "status":       "online",
        "groq_api_key": "SET" if groq_key else "MISSING",
        "groq_test":    groq_test,
        "groq_status":  groq_status,
        "llm":          "Groq LLaMA 3",
        "llm_available": groq_key and GROQ_OK,
        "routing": {
            "all_features": "Groq LLaMA 3 (llama-3.3-70b-versatile)",
            "conversation": "Groq LLaMA 3 (llama-3.1-8b-instant)",
        }
    }

@app.get("/api/diagnose")
async def diagnose():
    results = {}
    groq_key = os.getenv("GROQ_API_KEY","").strip()

    results["GROQ_API_KEY"] = "✅ SET" if groq_key else "❌ MISSING"

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
    results["chromadb"] = "✅ OK" if CHROMA_OK else "⚠️ NOT INSTALLED"
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
    path     = request.get("resume_path", "") or request.get("file_path", "")
    job_desc = request.get("job_description", "") or request.get("job_query", "") or ""
    user_id  = request.get("user_id", "anon")

    if not path or not os.path.exists(path):
        raise HTTPException(404, f"Resume not found: {path}")

    text = extract_pdf_text(path)
    if not text or len(text) < 20:
        raise HTTPException(422, "Cannot extract text. Ensure PDF is not a scanned image.")

    # Calculate deterministic base score as ground truth for Gemini
    from utils.ats_scorer import calculate_real_ats_score
    ats_data = calculate_real_ats_score(text, job_desc)
    real_ats_score = ats_data["ats_score"]

    # Truncate to fit context window (keep first 3000 chars = full resume)
    text_truncated = text[:3000]

    system = (
        "You are an expert resume analyst and strict Applicant Tracking System (ATS) scorer. "
        "You calculate a real, fresh ATS score every single time from the actual resume content. "
        "You return ONLY valid JSON — no markdown, no backticks, no explanation."
    )

    prompt = f"""You are a strict and accurate ATS (Applicant Tracking System) scorer. 
Your job is to analyze the resume provided and return a REAL, 
calculated ATS score — not a generic or placeholder score.

CRITICAL RULES:
- Every resume MUST produce a DIFFERENT score based on its actual content
- NEVER return a hardcoded, default, or repeated score like 75 or 80
- The score must be calculated fresh every single time from the actual 
  resume text provided
- If two resumes are different, their scores MUST be different

OUR DETERMINISTIC PARSER EXTRACTED THE FOLLOWING GROUND TRUTH DATA:
- Keyword Score: {ats_data['score_breakdown']['keywords']}/40 (Keywords found: {ats_data['found_keywords']}, Missing: {ats_data['missing_keywords'][:15]})
- Required Sections Score: {ats_data['score_breakdown']['sections']}/25 (Missing: {ats_data['missing_sections']})
- Quantification/Metrics Score: {ats_data['score_breakdown']['quantification']}/20 (Quantified statements found: {ats_data['quantified_achievements_count']})
- Formatting Score: {ats_data['score_breakdown']['format']}/15 (Formatting issues: {ats_data['feedback']})

CRITICAL GRADING RULES:
1. You MUST base your category score calculations on the above factual parser data.
2. If the quantification statements count is 0, you MUST score "experience_quality" as 0 (out of 20).
3. If there are formatting issues, missing email, or missing phone, you MUST penalize the "formatting" score heavily.
4. Calculate the final `ats_score` strictly using the sum of the categories (out of 100). The final score should be extremely close to the base score of {real_ats_score} unless you find additional visual/reading flow issues. Do NOT artificially inflate the score. Be a harsh grader like a top tier company recruiter.

HOW TO CALCULATE THE SCORE (out of 100):

1. KEYWORD DENSITY (30 points)
   - Extract all skills, tools, technologies, job titles from the resume
   - Count how many relevant industry keywords are present
   - More relevant keywords = higher points (0–30)

2. FORMATTING & PARSABILITY (20 points)
   - Does it use standard section headers? (Experience, Education, Skills)
   - Is it free of tables, columns, graphics, text boxes?
   - Is contact info clearly visible?
   - Deduct points for each formatting issue found

3. WORK EXPERIENCE QUALITY (20 points)
   - Are achievements quantified? (e.g., "increased sales by 30%")
   - Are strong action verbs used?
   - Is experience relevant and clearly described?
   - Vague bullet points = lower score (0 if no numbers/metrics found)

4. COMPLETENESS OF SECTIONS (15 points)
   - Has: Contact Info, Summary, Experience, Education, Skills?
   - Each missing section = deduct 3 points

5. EDUCATION & CERTIFICATIONS (10 points)
   - Relevant degree or certifications present?
   - Score based on relevance and completeness

6. LENGTH & READABILITY (5 points)
   - 1–2 pages = full points
   - Too short (<half page) or too long (>3 pages) = deduct points

CALCULATION:
- Add up the actual points earned in each category
- Final score = sum of all category scores
- Round to nearest whole number

OUTPUT FORMAT (return this exact JSON):
{{
  "ats_score": <calculated number between 0 and 100>,
  "breakdown": {{
    "keyword_density": <0-30>,
    "formatting": <0-20>,
    "experience_quality": <0-20>,
    "section_completeness": <0-15>,
    "education_certifications": <0-10>,
    "length_readability": <0-5>
  }},
  "keyword_gaps": ["list of important missing keywords"],
  "formatting_issues": ["list of specific formatting problems found"],
  "strengths": ["list of what this resume does well"],
  "suggestions": ["list of specific actionable improvements"],
  "experience_level": "junior | mid | senior",
  "skills_found": ["list of skills found"],
  "sections_detected": ["list of sections detected"]
}}

Target job description context (if any): {job_desc[:300] or 'General Industry Standard'}

RESUME TO ANALYZE:
{text_truncated}"""

    # Call Gemini 1.5 Flash using the user's specific Google API Key from environment
    gemini_key = os.getenv("GOOGLE_API_KEY", "").strip()
    raw = ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                f"System Instructions: {system}\n\nUser Prompt: {prompt}"
            )
        )
        raw = response.text or ""
    except Exception as e:
        print(f"⚠️ Gemini API key call failed: {e} — falling back to Groq")
        raw = await call_groq_async(
            prompt=prompt,
            system=system,
            model="llama-3.3-70b-versatile",
            max_tokens=800,
            temperature=0.2,
            timeout=25.0,
        )

    parsed = parse_json(raw, {
        "ats_score": 60,
        "breakdown": {
            "keyword_density": 18,
            "formatting": 14,
            "experience_quality": 12,
            "section_completeness": 9,
            "education_certifications": 5,
            "length_readability": 2
        },
        "keyword_gaps": [],
        "formatting_issues": [],
        "strengths": [],
        "suggestions": ["Analysis failed to parse — verify API keys"],
        "experience_level": "junior",
        "skills_found": [],
        "sections_detected": ["Education", "Experience", "Skills"]
    })

    # Map the Gemini outputs to React UI keys
    ats_val = parsed.get("ats_score", 60)
    user_breakdown = parsed.get("breakdown", {})
    
    # Standard grade bands
    if ats_val >= 85:
        grade = "A"
    elif ats_val >= 70:
        grade = "B"
    elif ats_val >= 50:
        grade = "C"
    else:
        grade = "D"

    # Map categories to match 40, 25, 20, 15 scale expected by frontend UI
    mapped_breakdown = {
        "keywords":       round((user_breakdown.get("keyword_density", 18) / 30.0) * 40.0),
        "sections":       round((user_breakdown.get("section_completeness", 10) / 15.0) * 25.0),
        "quantification": round(user_breakdown.get("experience_quality", 12)),
        "format":         round((user_breakdown.get("formatting", 12) / 20.0) * 15.0)
    }

    result = {
        "overall_score":     ats_val,
        "overall_grade":     grade,
        "ats_score":         ats_val,
        "ats_breakdown":     mapped_breakdown,
        "experience_level":  parsed.get("experience_level") or "junior",
        "skills_found":      parsed.get("skills_found") or [],
        "skill_gaps":        parsed.get("keyword_gaps") or [],
        "missing_keywords":  parsed.get("keyword_gaps") or [],
        "missing_sections":  list(set(["Contact Info", "Summary", "Experience", "Education", "Skills"]) - set(parsed.get("sections_detected", []))),
        "sections_detected": parsed.get("sections_detected") or ["Education", "Experience", "Skills"],
        "suggestions":       parsed.get("suggestions") or [],
        "feedback":          (parsed.get("formatting_issues") or []) + (parsed.get("suggestions") or []),
        "grade":             grade,
        "resume_text":       text
    }

    _cache[f"analysis:{user_id}"] = result
    _cache[f"text:{path}"]        = text
    return result

@app.get("/jobs")
@app.get("/api/jobs")
async def get_jobs(q: str = "Software Engineer", location: str = "India", user_id: str = "anon"):
    import httpx
    jobs = []

    # Fetch jobs (unchanged — no LLM needed for fetching)
    rk = os.getenv("RAPIDAPI_KEY","").strip()
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
                        "id": j.get("job_id",""),
                        "title": j.get("job_title",""),
                        "company": j.get("employer_name",""),
                        "location": j.get("job_city", location),
                        "description": (j.get("job_description") or "")[:400],
                        "apply_link": j.get("job_apply_link","#"),
                        "salary": "",
                        "source": "jsearch",
                        "match_score": 0,
                    })
        except Exception as e:
            print(f"JSearch error: {e}")

    # Demo fallback
    if not jobs:
        jobs = [
            {"id":"d1","title":f"Senior {q}","company":"TechCorp India","location":location,"description":f"Senior {q} with Python, React, FastAPI. 2+ years exp.","apply_link":"https://linkedin.com/jobs","salary":"12-20 LPA","source":"demo","match_score":88,"matched_skills":["Python","React"],"missing_skills":["Docker"],"recommendation":"Strong match"},
            {"id":"d2","title":f"AI/ML {q}","company":"InnovateTech","location":"Hyderabad","description":f"AI {q} role. LangChain, Gemini, RAG, FastAPI.","apply_link":"https://linkedin.com/jobs","salary":"8-15 LPA","source":"demo","match_score":92,"matched_skills":["LangChain","Python"],"missing_skills":[],"recommendation":"Excellent match"},
            {"id":"d3","title":f"Full Stack {q}","company":"GlobalTech","location":"Remote","description":f"Remote {q}. React, Node.js, Python, Docker.","apply_link":"https://linkedin.com/jobs","salary":"10-18 LPA","source":"demo","match_score":78,"matched_skills":["React","Python"],"missing_skills":["AWS"],"recommendation":"Good match"},
            {"id":"d4","title":f"Junior {q}","company":"StartupXYZ","location":"Mumbai","description":f"Junior {q} for freshers. React, Python, Firebase.","apply_link":"https://linkedin.com/jobs","salary":"4-8 LPA","source":"demo","match_score":82,"matched_skills":["React","Python","Firebase"],"missing_skills":[],"recommendation":"Great entry-level fit"},
            {"id":"d5","title":f"Backend {q}","company":"FinTech Corp","location":"Pune","description":f"Backend {q}. Python, FastAPI, PostgreSQL.","apply_link":"https://linkedin.com/jobs","salary":"8-14 LPA","source":"demo","match_score":74,"matched_skills":["Python","FastAPI"],"missing_skills":["PostgreSQL"],"recommendation":"Good match"},
            {"id":"d6","title":f"{q} Intern","company":"MNC Corp","location":"Ahmedabad","description":f"6-month {q} internship. Python, JavaScript.","apply_link":"https://linkedin.com/jobs","salary":"15000-25000/month","source":"demo","match_score":76,"matched_skills":["Python","JavaScript"],"missing_skills":[],"recommendation":"Good for freshers"},
        ]

    # Score with Groq if profile available
    analysis = _cache.get(f"analysis:{user_id}", {})
    skills   = analysis.get("skills_found", [])

    if skills and GROQ_OK and os.getenv("GROQ_API_KEY"):
        profile = f"Skills: {', '.join(skills[:10])}. Level: {analysis.get('experience_level','junior')}"

        async def score_one(job):
            try:
                raw = await call_groq_async(
                    prompt=(
                        f"Rate job fit 0-100. Return ONLY JSON.\n"
                        f"Profile: {profile}\n"
                        f"Job: {job['title']} — {job['description'][:150]}\n"
                        f'{{"match_score":75,"matched_skills":["Python"],"missing_skills":["Docker"],"recommendation":"Good match"}}'
                    ),
                    model="llama-3.1-8b-instant",
                    max_tokens=150,
                    temperature=0.1,
                    timeout=8.0,
                )
                scored = parse_json(raw, {})
                if scored.get("match_score"):
                    job.update(scored)
            except Exception:
                pass
            return job

        scored = await asyncio.gather(*[score_one(j) for j in jobs[:6]], return_exceptions=True)
        for i, r in enumerate(scored):
            if isinstance(r, dict):
                jobs[i] = r

    jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return {"jobs": jobs, "count": len(jobs), "source": jobs[0].get("source","demo") if jobs else "none"}

# ── Rewrite Resume ─────────────────────────────────────────────────
@app.post("/rewrite")
@app.post("/api/rewrite")
async def rewrite_resume(request: dict):
    path      = request.get("resume_path", "") or request.get("file_path", "")
    job       = request.get("job", {})
    job_title = str(job.get("title") or "Software Engineer")
    job_desc  = str(job.get("description") or "")[:400]

    if not path or not os.path.exists(path):
        raise HTTPException(404, f"Resume not found: {path}")

    original_text = _cache.get(f"text:{path}") or extract_pdf_text(path)
    _cache[f"text:{path}"] = original_text

    # Smart truncation for Groq context limit
    # Keep full resume — 3000 chars covers any resume
    resume_truncated = original_text[:3000]

    system = (
        "You are a professional resume writer improving ATS scores. "
        "You follow instructions exactly. You return only the resume text, nothing else."
    )

    prompt = (
        f"Rewrite this resume to maximize ATS score for the target job.\n\n"
        f"CRITICAL RULES — FOLLOW EXACTLY:\n"
        f"1. Keep ALL section headers unchanged: Education, Experience, Projects, "
        f"Certifications, CORE SKILLS, Achievements and Positions of Responsibility\n"
        f"2. Keep ALL names, dates, companies, CGPA, percentages UNCHANGED\n"
        f"3. Keep ALL bullet markers (•) exactly as-is\n"
        f"4. NEVER add [Email] [LinkedIn] [GitHub] [Phone] placeholders\n"
        f"5. NEVER add or remove lines — same line count as input\n"
        f"6. ONLY improve bullet point descriptions and project descriptions\n"
        f"7. Add these keywords naturally: {job_desc[:200]}\n"
        f"8. Quantify vague statements with realistic numbers\n"
        f"9. Use action verbs: Built, Engineered, Deployed, Optimized, Implemented\n"
        f"10. Return ONLY the resume text — no explanation\n\n"
        f"Target Job: {job_title}\n\n"
        f"Original Resume:\n{resume_truncated}"
    )

    rewritten = await call_groq_async(
        prompt=prompt,
        system=system,
        model="llama-3.3-70b-versatile",
        max_tokens=2000,
        temperature=0.2,
        timeout=35.0,
    )

    if not rewritten or rewritten.startswith("ERROR:"):
        rewritten = original_text

    # Clean placeholders
    for pat in [r'\[Email\]', r'\[LinkedIn\]', r'\[GitHub\]',
                r'\[Phone\]', r'\[URL\]', r'\[Website\]']:
        rewritten = re.sub(pat, '', rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(r'\s*\|\s*\|\s*', ' ', rewritten)

    # ATS scoring
    from utils.ats_scorer import calculate_real_ats_score
    orig_ats_data = calculate_real_ats_score(original_text, job_desc)
    orig_ats_score = orig_ats_data["ats_score"]
    
    new_ats_data = calculate_real_ats_score(rewritten, job_desc)
    new_ats_score = new_ats_data["ats_score"]

    jw  = set(w.lower() for w in job_desc.split() if len(w) > 5)
    ow  = set(original_text.lower().split())
    nw  = set(rewritten.lower().split())
    kwa = list((jw & nw) - ow)[:12]

    # Build PDF preserving formatting
    pdf_path = None
    try:
        from tools.pdf_tool import pdf_handler
        pdf_bytes = pdf_handler.rebuild_pdf_with_rewritten_text(
            original_path=path,
            original_text=original_text,
            rewritten_text=rewritten,
        )
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            suffix=".pdf", prefix="rewritten_",
            dir="data/uploads", delete=False
        )
        tmp.write(pdf_bytes)
        tmp.close()
        pdf_path = tmp.name
    except Exception as e:
        print(f"⚠️ PDF rebuild failed: {e}")

    return {
        "original_text":      original_text,
        "rewritten_text":     rewritten,
        "keywords_added":     kwa,
        "rewritten_pdf_path": pdf_path,
        "changes_summary": [
            f"Added {len(kwa)} ATS keywords from job description",
            "Strengthened bullet points with action verbs",
            "Preserved exact original formatting",
            "Quantified achievements where possible",
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
    # First try pre-built PDF from rewrite step
    pdf_path      = request.get("rewritten_pdf_path", "")
    rewritten_text = request.get("rewritten_text", "")
    original_path  = request.get("resume_path", "")
    original_text  = request.get("original_text", "")

    # Option 1: Use pre-built PDF file
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="rewritten_resume.pdf"'}
        )

    # Option 2: Rebuild on demand from original + rewritten text
    if original_path and os.path.exists(original_path) and rewritten_text:
        try:
            from tools.pdf_tool import pdf_handler
            if not original_text:
                original_text = pdf_handler.extract_text_for_ai(original_path)
            pdf_bytes = pdf_handler.rebuild_pdf_with_rewritten_text(
                original_path=original_path,
                original_text=original_text,
                rewritten_text=rewritten_text,
            )
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type="application/pdf",
                headers={"Content-Disposition": 'attachment; filename="rewritten_resume.pdf"'}
            )
        except Exception as e:
            print(f"PDF rebuild failed: {e}")

    # Option 3: Fallback — wrap rewritten text in simple PDF
    if rewritten_text:
        try:
            from reportlab.pdfgen import canvas as rl
            from reportlab.lib.pagesizes import A4
            buf   = io.BytesIO()
            c     = rl.Canvas(buf, pagesize=A4)
            W, H  = A4
            c.setFont("Helvetica", 10)
            y = H - 50
            for line in rewritten_text.split("\n"):
                if y < 50:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y = H - 50
                c.drawString(40, y, line[:110])
                y -= 13
            c.save()
            buf.seek(0)
            return StreamingResponse(
                buf,
                media_type="application/pdf",
                headers={"Content-Disposition": 'attachment; filename="rewritten_resume.pdf"'}
            )
        except ImportError:
            pass

    raise HTTPException(400, "No PDF content available to download")

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
        model="llama-3.3-70b-versatile",  # smarter model for better questions
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
        model="llama-3.3-70b-versatile",
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
        model="llama-3.1-8b-instant",
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
        model="llama-3.3-70b-versatile",
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
        client = get_groq()
        if client:
            loop   = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client.chat.completions.create(
                        model="llama-3.1-8b-instant",
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
        print(f"⚠️ Groq coach failed: {e}")
        # Fallback to general Groq wrapper (will try rate-limit fallback too)
        hist_str = "\n".join(
            f"{m.get('role','').upper()}: {m.get('content','')[:60]}"
            for m in (history or [])[-4:]
            if isinstance(m, dict)
        )
        groq_prompt = (
            f"You are Aria, a warm English coach. Have a natural 2-3 sentence conversation reply. "
            f"End with a question. No lists or bullet points.\n\n"
            f"History:\n{hist_str}\n\n"
            f"Student: {msg}\n\nAria:"
        )
        reply = await call_groq_async(
            prompt=groq_prompt,
            system="You are Aria, a warm English coach.",
            model="llama-3.1-8b-instant",
            max_tokens=200,
            temperature=0.85,
            timeout=10.0
        )

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
        model="llama-3.3-70b-versatile",
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
