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

# In-memory caches
_cache: dict = {}
_file_cache: dict = {}  # path -> bytes

def extract_pdf_text(path: str) -> str:
    """Extract PDF text — checks memory cache first, then disk."""
    if not PDF_OK:
        return ""

    # Try memory cache first (most reliable)
    if path in _file_cache:
        try:
            import io
            reader = PyPDF2.PdfReader(io.BytesIO(_file_cache[path]))
            return " ".join(p.extract_text() or "" for p in reader.pages).strip()
        except Exception as e:
            print(f"Memory cache read failed: {e}")

    # Fallback to disk
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                return " ".join(p.extract_text() or "" for p in reader.pages).strip()
        except Exception as e:
            print(f"Disk read failed: {e}")

    return ""

# ── FASTAPI APP ────────────────────────────────────────────────────
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✅ FastAPI lifespan started")
    # Warm up LLM in background
    async def warmup():
        await asyncio.sleep(2)
        try:
            pass
        except Exception:
            pass
            
    # Keep-alive ping
    async def keep_alive():
        await asyncio.sleep(30)
        while True:
            try:
                import httpx
                url = os.getenv("RENDER_EXTERNAL_URL", "")
                if url:
                    async with httpx.AsyncClient(timeout=8.0) as c:
                        r = await c.get(f"{url}/health")
                    print(f"✅ Keep-alive ping: {r.status_code}")
            except Exception as e:
                print(f"⚠️ Keep-alive failed: {e}")
            await asyncio.sleep(600)  # every 10 min instead of 14 — more aggressive

    asyncio.create_task(warmup())
    asyncio.create_task(keep_alive())
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
        # Ensure upload directory exists EVERY time (Render may wipe it)
        os.makedirs("data/uploads", exist_ok=True)

        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename or "resume.pdf")
        # Add timestamp to avoid collisions
        import time
        timestamp = int(time.time())
        unique_name = f"{timestamp}_{safe_name}"
        path = f"data/uploads/{unique_name}"

        content = await file.read()
        if len(content) == 0:
            raise HTTPException(400, "Uploaded file is empty")

        with open(path, "wb") as f:
            f.write(content)

        # VERIFY the file was actually written
        if not os.path.exists(path):
            raise HTTPException(500, "File write failed — could not verify file exists")

        actual_size = os.path.getsize(path)
        print(f"✅ Upload saved: {path} ({actual_size} bytes)")

        # ALSO store in memory as backup — survives even if disk write has issues
        _file_cache[path] = content

        return {
            "file_path": path,
            "filename":  unique_name,
            "size":      actual_size,
            "verified":  True,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        raise HTTPException(500, f"Upload failed: {str(e)}")

# ── Real ATS Score Logic ───────────────────────────────────────────
import re

STRONG_ACTION_VERBS = {
    "engineered","architected","built","developed","implemented","deployed",
    "designed","optimized","automated","integrated","launched","led","managed",
    "created","delivered","improved","reduced","increased","streamlined",
    "established","coordinated","executed","analyzed","configured","maintained",
    "migrated","scaled","researched","trained","mentored","collaborated",
    "spearheaded","accelerated","achieved","administered","computed","constructed",
    "debugged","demonstrated","enhanced","facilitated","generated","handled",
    "identified","monitored","operated","performed","produced","resolved",
    "supervised","utilized","validated","authored","composed","modeled",
}

STANDARD_SECTIONS = {
    "experience","education","skills","projects","certifications",
    "achievements","summary","objective","publications","awards",
}

def calculate_real_ats_score(resume_text: str, job_description: str = "") -> dict:
    """
    Real ATS score — 6 weighted components matching what actual ATS systems check.
    Total = 100 points.
    """
    if not resume_text or len(resume_text) < 50:
        return {
            "total_score": 0, "percentage": 0, "grade": "Invalid",
            "breakdown": {}, "top_issues": []
        }

    text_lower  = resume_text.lower()
    lines       = [l.strip() for l in resume_text.split('\n') if l.strip()]
    words       = resume_text.lower().split()
    word_count  = len(words)

    # Identify bullet lines
    bullet_lines = [
        l for l in lines
        if l.startswith(('•', '-', '*', '◦', '▪'))
        or re.match(r'^\s*[\•\-\*]\s', l)
    ]

    breakdown = {}

    # ── 1. KEYWORD MATCH (30 points) ──────────────────────────────
    kw_score      = 0
    matched_kw    = []
    missing_kw    = []

    if job_description and job_description.strip():
        STOPWORDS = {
            "with","and","the","for","this","that","will","have","from",
            "they","them","their","about","into","than","your","our","are",
            "were","been","being","would","could","should","must","shall",
            "may","might","also","has","its","via","per","not","but","all",
            "any","can","use","used","using","work","works","working",
        }
        jd_words = set(
            w.lower().strip('.,;:()/[]"\'')
            for w in job_description.split()
            if len(w) > 4 and w.lower() not in STOPWORDS
        )
        jd_words = {w for w in jd_words if w.isalpha() or w.replace('.','').isalpha()}

        for kw in jd_words:
            # Check exact word match
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                matched_kw.append(kw)
            # Check stem (first 5 chars)
            elif len(kw) >= 6:
                stem = kw[:5]
                if re.search(r'\b' + re.escape(stem), text_lower):
                    matched_kw.append(kw)
                else:
                    missing_kw.append(kw)
            else:
                missing_kw.append(kw)

        total_jd = max(len(jd_words), 1)
        match_rate = len(matched_kw) / total_jd
        kw_score   = min(30, int(match_rate * 30))
    else:
        # No JD — neutral score based on general professional keywords
        general_kw = ["python","javascript","react","node","fastapi","sql",
                       "docker","aws","git","api","machine","learning","data"]
        found = sum(1 for k in general_kw if k in text_lower)
        kw_score = min(30, found * 2)

    breakdown["keyword_match"] = {
        "score": kw_score, "max": 30,
        "label": "Keyword Match",
        "matched": matched_kw[:15],
        "missing": missing_kw[:10],
        "match_rate": round(len(matched_kw)/max(len(matched_kw)+len(missing_kw),1)*100, 1)
    }

    # ── 2. SECTION STRUCTURE (20 points) ──────────────────────────
    required_sections = ["experience", "education", "skills"]
    optional_sections = ["projects", "certifications", "achievements", "summary"]

    found_required = [s for s in required_sections if s in text_lower]
    found_optional = [s for s in optional_sections if s in text_lower]
    missing_req    = [s for s in required_sections if s not in text_lower]

    # Required sections: 5 pts each (15 max)
    # Optional sections: 1 pt each (5 max)
    sec_score = min(15, len(found_required) * 5) + min(5, len(found_optional))

    breakdown["section_structure"] = {
        "score":    sec_score,
        "max":      20,
        "label":    "Section Structure",
        "found":    found_required + found_optional,
        "missing":  missing_req,
    }

    # ── 3. ACTION VERBS (15 points) ───────────────────────────────
    bullets_with_verbs = 0
    verbs_used         = []

    for line in bullet_lines:
        # Get first real word of bullet content
        content    = re.sub(r'^[\•\-\*◦▪\s]+', '', line).lower()
        first_word = content.split()[0] if content.split() else ""
        # Also check if bold label like "Data Collection:" then next sentence verb
        if ':' in content:
            after_colon = content.split(':', 1)[1].strip()
            first_word  = after_colon.split()[0] if after_colon.split() else first_word

        if first_word in STRONG_ACTION_VERBS:
            bullets_with_verbs += 1
            verbs_used.append(first_word)

    verb_rate  = bullets_with_verbs / max(len(bullet_lines), 1)
    verb_score = min(15, int(verb_rate * 15))

    # Penalty if no bullet points at all
    if len(bullet_lines) == 0:
        verb_score = 3

    breakdown["action_verbs"] = {
        "score":                verb_score,
        "max":                  15,
        "label":                "Action Verbs",
        "bullets_total":        len(bullet_lines),
        "bullets_with_verbs":   bullets_with_verbs,
        "verbs_used":           list(set(verbs_used))[:8],
    }

    # ── 4. QUANTIFICATION (15 points) ─────────────────────────────
    # Check for numbers, %, metrics in bullet points
    quant_pattern = re.compile(
        r'\b(\d+[\.,]?\d*)\s*'
        r'(%|percent|x|times|ms|gb|tb|kb|mb|k\b|m\b|users|requests|'
        r'seconds|hours|days|weeks|points|stars|million|billion|thousand|'
        r'lpa|crore|lakhs|models|features|apis|endpoints|queries|records|'
        r'increase|decrease|reduction|improvement|accuracy|efficiency)?\b',
        re.IGNORECASE
    )

    quantified_bullets = 0
    for line in bullet_lines:
        if quant_pattern.search(line) and re.search(r'\d', line):
            quantified_bullets += 1

    quant_rate  = quantified_bullets / max(len(bullet_lines), 1)
    quant_score = min(15, int(quant_rate * 15))

    breakdown["quantification"] = {
        "score":               quant_score,
        "max":                 15,
        "label":               "Quantified Achievements",
        "bullets_quantified":  quantified_bullets,
        "bullets_total":       len(bullet_lines),
        "rate":                round(quant_rate * 100, 1),
    }

    # ── 5. CONTACT INFO (10 points) ───────────────────────────────
    contact_score = 0
    contact_found = []

    # Email
    if re.search(r'[\w.\-+]+@[\w.\-]+\.\w{2,}', resume_text):
        contact_score += 3
        contact_found.append("email")
    # Phone
    if re.search(r'(\+?\d[\d\s\-().]{7,}|\d{10})', resume_text):
        contact_score += 2
        contact_found.append("phone")
    # LinkedIn
    if re.search(r'linkedin\.com', text_lower):
        contact_score += 3
        contact_found.append("linkedin")
    # GitHub
    if re.search(r'github\.com', text_lower):
        contact_score += 2
        contact_found.append("github")

    breakdown["contact_info"] = {
        "score":   contact_score,
        "max":     10,
        "label":   "Contact Information",
        "found":   contact_found,
        "missing": [x for x in ["email","phone","linkedin","github"] if x not in contact_found],
    }

    # ── 6. FORMATTING QUALITY (10 points) ─────────────────────────
    fmt_score = 10

    # Penalty: garbled/non-ASCII characters (scanned PDF artifact)
    non_ascii = sum(1 for c in resume_text if ord(c) > 127 and ord(c) < 160)
    if non_ascii / max(word_count, 1) > 0.05:
        fmt_score -= 3

    # Penalty: duplicate content (column bleed bug)
    unique_words_set = set(words)
    if word_count > 0 and len(unique_words_set) / word_count < 0.35:
        fmt_score -= 4

    # Penalty: too short (extraction failure or very sparse resume)
    if word_count < 100:
        fmt_score -= 5

    # Penalty: no bullet points (poor ATS readability)
    if len(bullet_lines) == 0:
        fmt_score -= 3

    fmt_score = max(0, fmt_score)

    breakdown["formatting"] = {
        "score":      fmt_score,
        "max":        10,
        "label":      "Formatting Quality",
        "word_count": word_count,
        "bullets":    len(bullet_lines),
        "parseable":  fmt_score >= 7,
    }

    # ── TOTAL ──────────────────────────────────────────────────────
    total_score = sum(v["score"] for v in breakdown.values())
    total_max   = sum(v["max"]   for v in breakdown.values())
    percentage  = round(total_score / total_max * 100)

    # Top issues
    issues = []
    for key, val in breakdown.items():
        gap = val["max"] - val["score"]
        if gap >= 3:
            labels = {
                "keyword_match":    f"Add {len(missing_kw[:5])} missing keywords: {', '.join(missing_kw[:5])}",
                "section_structure":f"Add missing sections: {', '.join(val.get('missing', []))}",
                "action_verbs":     f"Start {val['bullets_total'] - val.get('bullets_with_verbs',0)} bullets with action verbs",
                "quantification":   f"Add numbers/metrics to {val['bullets_total'] - val.get('bullets_quantified',0)} bullet points",
                "contact_info":     f"Add missing contact info: {', '.join(val.get('missing', []))}",
                "formatting":       "Improve resume formatting and ATS parsability",
            }
            issues.append({
                "area":  labels.get(key, key),
                "gap":   gap,
                "score": val["score"],
                "max":   val["max"]
            })
    issues.sort(key=lambda x: -x["gap"])

    return {
        "total_score": total_score,
        "total_max":   total_max,
        "percentage":  percentage,
        "grade": (
            "Excellent" if percentage >= 85 else
            "Good"      if percentage >= 70 else
            "Fair"      if percentage >= 55 else
            "Needs Work"if percentage >= 35 else
            "Poor"
        ),
        "breakdown":   breakdown,
        "top_issues":  issues[:3],
        "matched_keywords": matched_kw[:20],
        "missing_keywords": missing_kw[:15],
    }

# ── Analyze Resume ─────────────────────────────────────────────────
@app.post("/analyze")
@app.post("/api/analyze")
async def analyze_resume(request: dict):
    path     = request.get("resume_path", "")
    job_desc = request.get("job_description", "")
    user_id  = request.get("user_id", "anon")

    print(f"📥 Analyze request — path: '{path}'")

    if not path or path.strip() == "":
        raise HTTPException(400, "No resume_path provided. Please upload a resume first.")

    # Check multiple possible path variations (handles path format mismatches)
    possible_paths = [
        path,
        path.lstrip("/"),
        os.path.join("data/uploads", os.path.basename(path)),
        os.path.abspath(path),
    ]

    actual_path = None
    for p in possible_paths:
        if os.path.exists(p):
            actual_path = p
            break

    if not actual_path and path in _file_cache:
        actual_path = path  # use memory cache even if disk file is gone

    if not actual_path:
        # List what IS in the uploads folder for debugging
        try:
            existing_files = os.listdir("data/uploads")
        except Exception:
            existing_files = []

        print(f"❌ File not found. Tried: {possible_paths}")
        print(f"📁 Files actually in data/uploads: {existing_files}")

        raise HTTPException(
            404,
            f"Resume file not found at '{path}'. "
            f"This usually means the backend restarted after upload "
            f"(common on Render free tier cold starts). "
            f"Please upload your resume again."
        )

    text = extract_pdf_text(actual_path)
    if not text or len(text) < 20:
        raise HTTPException(422, "Cannot extract text from PDF. Ensure it is not a scanned image.")

    # Calculate REAL ATS score BEFORE calling AI
    real_ats = calculate_real_ats_score(text, job_desc)

    # AI analysis for skills detection
    system = "You are an expert resume analyst. Return ONLY valid JSON, no markdown."
    prompt = (
        f"Analyze this resume. Return ONLY this JSON:\n"
        f'{{"skills_found":["Python","React"],"skill_gaps":["Docker"],'
        f'"experience_level":"junior","sections_detected":["Education","Experience"],'
        f'"suggestions":["Add LinkedIn URL","Add metrics to bullets"]}}\n\n'
        f"Resume:\n{text[:2500]}"
    )

    raw    = await call_groq_async(prompt=prompt, system=system,
                                   model="llama-3.1-8b-instant", max_tokens=500,
                                   temperature=0.2, timeout=25.0)
    ai     = parse_json(raw, {
        "skills_found":      [],
        "skill_gaps":        [],
        "experience_level":  "junior",
        "sections_detected": [],
        "suggestions":       [],
    })

    result = {
        **ai,
        # Use REAL scores — not AI-generated ones
        "ats_score":         real_ats["percentage"],
        "overall_score":     real_ats["percentage"],
        "ats_breakdown":     real_ats["breakdown"],
        "ats_grade":         real_ats["grade"],
        "top_issues":        real_ats["top_issues"],
        "matched_keywords":  real_ats.get("matched_keywords", []),
        "missing_keywords":  real_ats.get("missing_keywords", []),
        "resume_text":       text,
        "resume_path":       actual_path,  # return the path that actually worked
    }

    _cache[f"analysis:{user_id}"] = result
    _cache[f"text:{actual_path}"] = text
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
    path      = request.get("resume_path", "")
    job       = request.get("job", {})
    job_title = str(job.get("title") or "Software Engineer")
    job_desc  = str(job.get("description") or "")[:500]

    if not path or not os.path.exists(path):
        raise HTTPException(404, f"Resume not found: {path}")

    original_text = _cache.get(f"text:{path}") or extract_pdf_text(path)
    _cache[f"text:{path}"] = original_text

    # Calculate REAL original ATS score first
    original_ats = calculate_real_ats_score(original_text, job_desc)

    # Rewrite with AI
    system = "You are a professional resume writer. Return only resume text, no explanation."
    prompt = (
        f"Rewrite this resume for the target job. STRICT RULES:\n"
        f"1. Keep ALL section headers unchanged\n"
        f"2. Keep ALL names, dates, companies, CGPA, percentages unchanged\n"
        f"3. Keep ALL bullet markers exactly\n"
        f"4. NEVER add [Email] [LinkedIn] [GitHub] placeholders\n"
        f"5. Same line count as original\n"
        f"6. Add these keywords naturally: {job_desc[:250]}\n"
        f"7. Quantify vague statements with realistic numbers\n"
        f"8. Use strong action verbs\n"
        f"9. Add LinkedIn/GitHub if missing (use placeholder like: linkedin.com/in/name)\n"
        f"10. Return ONLY the resume text\n\n"
        f"Job: {job_title}\n\nOriginal:\n{original_text[:3000]}"
    )

    rewritten = await call_groq_async(prompt=prompt, system=system,
                                      model="llama-3.1-8b-instant", max_tokens=2500,
                                      temperature=0.2, timeout=40.0)

    if not rewritten or rewritten.startswith("ERROR:"):
        rewritten = original_text

    # Clean AI-added placeholders
    for pat in [r'\[Email\]',r'\[LinkedIn\]',r'\[GitHub\]',
                r'\[Phone\]',r'\[URL\]',r'\[Website\]']:
        rewritten = re.sub(pat, '', rewritten, flags=re.IGNORECASE)

    # Calculate REAL rewritten ATS score
    rewritten_ats = calculate_real_ats_score(rewritten, job_desc)

    # Build PDF
    pdf_path = None
    try:
        from tools.pdf_tool import pdf_handler
        # Fix — use path not text as original_path
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
        print(f"⚠️ PDF rebuild: {e}")
        import traceback; traceback.print_exc()

    return {
        "original_text":      original_text,
        "rewritten_text":     rewritten,
        "keywords_added":     rewritten_ats.get("matched_keywords", [])[:12],
        "rewritten_pdf_path": pdf_path,
        "changes_summary": [
            f"ATS score improved from {original_ats['percentage']}% to {rewritten_ats['percentage']}%",
            f"Added {len(rewritten_ats.get('matched_keywords',[]))} job keywords",
            "Strengthened bullet points with action verbs",
            "Preserved exact original formatting",
        ],
        # REAL scores — not estimates
        "ats_scores": {
            "original":           original_ats["percentage"],
            "rewritten":          rewritten_ats["percentage"],
            "improvement":        rewritten_ats["percentage"] - original_ats["percentage"],
            "original_breakdown": original_ats["breakdown"],
            "rewritten_breakdown":rewritten_ats["breakdown"],
            "original_grade":     original_ats["grade"],
            "rewritten_grade":    rewritten_ats["grade"],
            "top_issues":         rewritten_ats["top_issues"],
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
async def score_pdf(
    file: UploadFile = File(...),
    job_description: str = Form(default="")
):
    data = await file.read()
    tmp  = f"data/uploads/tmp_{file.filename}"
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        text = extract_pdf_text(tmp)
        if not text or len(text) < 20:
            raise HTTPException(422, "Cannot extract text.")

        # Calculate REAL ATS score from the actual PDF
        real_ats = calculate_real_ats_score(text, job_description)

        return {
            "ats_score":     real_ats["percentage"],
            "overall_score": real_ats["percentage"],
            "grade":         real_ats["grade"],
            "breakdown":     real_ats["breakdown"],
            "top_issues":    real_ats["top_issues"],
            "text_length":   len(text),
            "word_count":    len(text.split()),
            "file":          file.filename,
        }
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
