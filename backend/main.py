"""
CareerMind AI — FastAPI Application
Exposes REST endpoints and WebSocket for real-time agent streaming.
"""
import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI, File, Form, HTTPException, Query, UploadFile,
    WebSocket, WebSocketDisconnect, Depends
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

import config as cfg
from db import init_db, get_session, upsert_session

from core.singletons import (
    get_llm, get_whisper, get_http_client, _init_skills_vectorstore, get_cache
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Lifespan context manager ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 CareerMind AI starting up...")
    try:
        await init_db()
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
    
    logger.info("⚡ Pre-warming LLMs...")
    try:
        get_llm()
        get_llm(quality=True)
    except Exception as e:
        logger.warning("LLM pre-warming failed: %s", e)
        
    logger.info("⚡ Pre-warming ChromaDB skills vectorstore...")
    try:
        _init_skills_vectorstore()
    except Exception as e:
        logger.warning("ChromaDB pre-warming failed: %s", e)
        
    logger.info("⚡ Pre-warming Whisper...")
    try:
        get_whisper()
    except Exception as e:
        logger.warning("Whisper pre-warming failed: %s", e)
        
    logger.info("✅ All systems ready — CareerMind AI is live!")
    yield
    # Shutdown
    try:
        await get_http_client().aclose()
    except Exception:
        pass
    logger.info("👋 CareerMind AI shut down cleanly")

# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CareerMind AI",
    description="Multi-agent AI Career Coach Platform API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add response compression middleware
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Security ───────────────────────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=cfg.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, cfg.SECRET_KEY, algorithm=cfg.ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """
    Validate JWT token. If no token provided, generate a guest user_id.
    This makes the app usable without auth for development.
    """
    if credentials is None:
        return f"guest-{uuid.uuid4().hex[:8]}"
    try:
        payload = jwt.decode(credentials.credentials, cfg.SECRET_KEY, algorithms=[cfg.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── WebSocket Manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info("WebSocket connected: user=%s", user_id)

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
            except ValueError:
                pass
        logger.info("WebSocket disconnected: user=%s", user_id)

    async def send_event(self, user_id: str, event: dict):
        if user_id in self.active_connections:
            dead = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(event)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                try:
                    self.active_connections[user_id].remove(ws)
                except ValueError:
                    pass


manager = ConnectionManager()

# ── Pydantic models ────────────────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    file_path: str
    user_id: Optional[str] = None
    job_query: Optional[str] = "Software Engineer"
    job_location: Optional[str] = "United States"


class RewriteRequest(BaseModel):
    resume_path: Optional[str] = None
    resume_text: Optional[str] = None
    job: dict
    user_id: Optional[str] = None


class InterviewQuestionRequest(BaseModel):
    job_title: str
    round_number: int = 1
    history: Optional[list] = []
    interview_type: Optional[str] = "mixed"
    type_instruction: Optional[str] = ""
    company: Optional[str] = ""
    level: Optional[str] = ""


class InterviewScoreRequest(BaseModel):
    question: str
    answer_text: str
    job_title: str


class AuthRequest(BaseModel):
    user_id: Optional[str] = None


# ── Startup / Shutdown ─────────────────────────────────────────────────────────


# ── Auth endpoint ──────────────────────────────────────────────────────────────
@app.post("/api/auth/token")
async def get_token(body: AuthRequest):
    """Generate a JWT token for a user_id."""
    user_id = body.user_id or f"user-{uuid.uuid4().hex[:12]}"
    token = create_access_token(user_id)
    await upsert_session(user_id, current_step="idle")
    return {"access_token": token, "token_type": "bearer", "user_id": user_id}


# ── Resume Upload ─────────────────────────────────────────────────────────────
@app.post("/api/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    user_id: str = Form(default=""),
    current_user: str = Depends(get_current_user),
):
    """Save uploaded PDF and return file path."""
    effective_user = user_id or current_user

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Save file
    safe_name = f"{effective_user}_{uuid.uuid4().hex[:8]}.pdf"
    file_path = os.path.join(cfg.UPLOADS_DIR, safe_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    await upsert_session(effective_user, resume_path=file_path)
    logger.info("Resume uploaded: %s (%d bytes)", file_path, len(content))

    return {
        "file_path": file_path,
        "filename": file.filename,
        "size_bytes": len(content),
        "user_id": effective_user,
    }


# ── Resume Analysis ───────────────────────────────────────────────────────────
@app.post("/api/analyze")
async def analyze_resume_endpoint(
    body: AnalyzeRequest,
    current_user: str = Depends(get_current_user),
):
    """Run resume analyzer. Returns full analysis dict."""
    from agents.resume_analyzer import analyze_resume, calculate_real_ats_score, calculate_overall_score, extract_pdf_text
    from tools.pdf_tool import pdf_handler
    from core.singletons import get_cache

    user_id = body.user_id or current_user

    if not body.file_path or not os.path.exists(body.file_path):
        raise HTTPException(status_code=404, detail="Resume file not found")

    # Progress events → WebSocket
    async def ws_callback(msg: str):
        await manager.send_event(user_id, {
            "agent": "Resume Analyzer",
            "status": "working",
            "message": msg,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def sync_callback(msg: str):
        asyncio.create_task(ws_callback(msg))

    await manager.send_event(user_id, {
        "agent": "Resume Analyzer",
        "status": "thinking",
        "message": "Starting resume analysis pipeline...",
        "timestamp": datetime.utcnow().isoformat(),
    })

    # ALWAYS extract text using optimized cached extraction
    fresh_text = extract_pdf_text(body.file_path)

    if not fresh_text or len(fresh_text) < 100:
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from PDF. Make sure the PDF is not scanned/image-based."
        )

    # Run AI analysis for skills, gaps, suggestions
    ai_analysis = await analyze_resume(body.file_path, user_id=user_id, progress_callback=sync_callback)

    # Calculate REAL ATS and Overall score from the actual extracted text
    session = await get_session(user_id)
    job_description = ""
    if session and session.get("selected_job"):
        job_description = session["selected_job"].get("description", "")

    ats_result = calculate_real_ats_score(fresh_text, job_description)
    overall_result = calculate_overall_score(fresh_text, job_description)

    # Update scores in the analysis dict to reflect real calculations
    result = {
        **ai_analysis,
        "ats_score": ats_result["percentage"],
        "ats_breakdown": ats_result["breakdown"],
        "overall_score": overall_result["overall_score"],
        "overall_breakdown": overall_result["breakdown"],
        "overall_grade": overall_result["grade"],
        "ats": ats_result,  # For backward compatibility
    }

    # Cache for this user so job scraper can use it
    get_cache()[f"latest_analysis:{user_id}"] = result

    # Save to SQLite
    await upsert_session(
        user_id,
        resume_path=body.file_path,
        resume_text=fresh_text,
        resume_analysis=result,
        current_step="resume_analyzed",
    )

    await manager.send_event(user_id, {
        "agent": "Resume Analyzer",
        "status": "done",
        "message": f"Analysis complete! Score: {result.get('overall_score', 0)}/100",
        "timestamp": datetime.utcnow().isoformat(),
    })

    return result


# ── Job Matching ──────────────────────────────────────────────────────────────
@app.get("/api/jobs")
async def get_jobs(
    q: str = Query(default="Software Engineer", description="Job title/keywords"),
    location: str = Query(default="United States", description="Job location"),
    user_id: str = Query(default=""),
    current_user: str = Depends(get_current_user),
):
    """Scrape and score job listings using optimized parallel async scraper."""
    from agents.job_scraper import scrape_and_score
    from core.singletons import get_cache

    effective_user = user_id or current_user

    # Try memory cache first, else get from DB session
    cache = get_cache()
    cache_key_analysis = f"latest_analysis:{effective_user}"
    resume_analysis = cache.get(cache_key_analysis)
    
    if not resume_analysis:
        session = await get_session(effective_user)
        resume_analysis = session.get("resume_analysis") if session else {}
    
    if not resume_analysis:
        resume_analysis = {"skills_found": [], "experience_level": "junior"}

    async def ws_callback(msg: str):
        await manager.send_event(effective_user, {
            "agent": "Job Scraper",
            "status": "working",
            "message": msg,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def sync_callback(msg: str):
        asyncio.create_task(ws_callback(msg))

    await manager.send_event(effective_user, {
        "agent": "Job Scraper",
        "status": "thinking",
        "message": f"Searching for '{q}' jobs in {location}...",
        "timestamp": datetime.utcnow().isoformat(),
    })

    # Run the optimized parallel async scraper
    jobs = await scrape_and_score(
        query=q,
        location=location,
        resume_analysis=resume_analysis,
        progress_callback=sync_callback,
    )

    await upsert_session(effective_user, job_listings=jobs, current_step="jobs_scraped")

    await manager.send_event(effective_user, {
        "agent": "Job Scraper",
        "status": "done",
        "message": f"Found {len(jobs)} matched jobs!",
        "timestamp": datetime.utcnow().isoformat(),
    })

    return {"jobs": jobs, "total": len(jobs), "query": q, "location": location}


# ── Resume Rewriter ───────────────────────────────────────────────────────────
@app.post("/api/rewrite")
async def rewrite_resume_endpoint(
    body: RewriteRequest,
    current_user: str = Depends(get_current_user),
):
    """Rewrite resume for a specific job."""
    from agents.resume_rewriter import rewrite_resume
    from agents.resume_analyzer import calculate_real_ats_score, extract_pdf_text
    from tools.pdf_tool import pdf_handler

    user_id = body.user_id or current_user

    # Get resume path from body or session
    resume_path = body.resume_path or ""
    if not resume_path:
        session = await get_session(user_id)
        resume_path = session.get("resume_path", "") if session else ""

    if not resume_path or not os.path.exists(resume_path):
        raise HTTPException(status_code=404, detail="Resume file not found")

    # Extract original text cached from the PDF
    original_text = extract_pdf_text(resume_path)

    # Score the ORIGINAL from its actual text
    job_description = body.job.get("description", "")
    original_ats = calculate_real_ats_score(original_text, job_description)

    async def ws_callback(msg: str):
        await manager.send_event(user_id, {
            "agent": "Resume Rewriter",
            "status": "working",
            "message": msg,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def sync_callback(msg: str):
        asyncio.create_task(ws_callback(msg))

    await manager.send_event(user_id, {
        "agent": "Resume Rewriter",
        "status": "thinking",
        "message": f"Rewriting resume for {body.job.get('title', 'selected role')}...",
        "timestamp": datetime.utcnow().isoformat(),
    })

    # Call the optimized async rewrite_resume function
    result = await rewrite_resume(resume_path, body.job, progress_callback=sync_callback)

    rewritten_text = result["rewritten_text"]

    # Score the REWRITTEN from its actual new text (not the original)
    rewritten_ats = calculate_real_ats_score(rewritten_text, job_description)

    ats_scores = {
        "original": original_ats["percentage"],
        "rewritten": rewritten_ats["percentage"],
        "improvement": round(rewritten_ats["percentage"] - original_ats["percentage"], 1),
        "original_breakdown": original_ats["breakdown"],
        "rewritten_breakdown": rewritten_ats["breakdown"],
        "original_grade": original_ats["grade"],
        "rewritten_grade": rewritten_ats["grade"],
        "top_issues_remaining": rewritten_ats["top_issues"]
    }

    result_with_ats = {
        **result,
        "ats_scores": ats_scores
    }

    await upsert_session(user_id, rewritten_resume=result_with_ats, selected_job=body.job)

    await manager.send_event(user_id, {
        "agent": "Resume Rewriter",
        "status": "done",
        "message": f"Resume rewritten with {len(result.get('changes_summary', []))} improvements!",
        "timestamp": datetime.utcnow().isoformat(),
    })

    return result_with_ats



@app.post("/api/rewrite/download-pdf")
async def download_rewritten_pdf(request: dict):
    import os
    import io
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse
    
    resume_path    = request.get("resume_path", "")
    rewritten_text = request.get("rewritten_text", "")
    original_text  = request.get("original_text", "")
    pdf_path       = request.get("rewritten_pdf_path", "")

    # If we have a pre-built PDF from rewrite, serve it directly
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="rewritten_resume.pdf"'}
        )

    # Rebuild on demand
    if resume_path and os.path.exists(resume_path) and rewritten_text:
        try:
            from tools.pdf_tool import pdf_handler
            pdf_bytes = pdf_handler.rebuild_pdf_with_rewritten_text(
                original_path=resume_path,
                original_text=original_text or pdf_handler.extract_text_for_ai(resume_path),
                rewritten_text=rewritten_text,
            )
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type="application/pdf",
                headers={"Content-Disposition": 'attachment; filename="rewritten_resume.pdf"'}
            )
        except Exception as e:
            print(f"PDF rebuild failed: {e}")

    # Fallback: wrap rewritten text in simple PDF
    try:
        from reportlab.pdfgen import canvas as rl
        from reportlab.lib.pagesizes import A4
        buf = io.BytesIO()
        c   = rl.Canvas(buf, pagesize=A4)
        w, h = A4
        c.setFont("Helvetica", 10)
        y = h - 50
        for line in (rewritten_text or "No content").split("\n"):
            line = line[:110]  # prevent overflow
            if y < 50:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = h - 50
            c.drawString(40, y, line)
            y -= 13
        c.save()
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="rewritten_resume.pdf"'}
        )
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {str(e)}")


@app.post("/api/score-pdf")
async def score_uploaded_pdf(
    file: UploadFile = File(...),
    job_description: str = Form(default="")
):
    """
    Accept any PDF upload and return its REAL ATS score and Overall Score.
    This is called when the user uploads the downloaded rewritten PDF
    to verify the score reflects the actual file content.
    """
    from agents.resume_analyzer import calculate_real_ats_score, calculate_overall_score
    from tools.pdf_tool import pdf_handler

    # Save temp file
    tmp_path = f"data/uploads/score_check_{file.filename}"
    content = await file.read()
    with open(tmp_path, "wb") as f:
        f.write(content)

    try:
        # Extract text fresh from this PDF
        text = pdf_handler.extract_text_for_ai(tmp_path)

        if not text or len(text) < 50:
            raise HTTPException(
                status_code=422,
                detail="Cannot extract text from this PDF. It may be scanned or image-based."
            )

        # Both scores calculated fresh from this PDF's actual text
        ats_result = calculate_real_ats_score(text, job_description)
        overall_result = calculate_overall_score(text, job_description)

        return {
            "ats_score": ats_result["percentage"],
            "overall_score": overall_result["overall_score"],
            "overall_grade": overall_result["grade"],
            "overall_breakdown": overall_result["breakdown"],
            "ats_breakdown": ats_result["breakdown"],
            "top_issues": ats_result["top_issues"],
            "text_length": len(text),
            "file": file.filename
        }
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ── Interview — Generate Question ─────────────────────────────────────────────
@app.post("/api/interview/question")
async def get_interview_question(
    body: InterviewQuestionRequest,
    current_user: str = Depends(get_current_user),
):
    """Generate the next interview question. Browser handles TTS via Web Speech API."""
    from agents.mock_interviewer import generate_question

    loop = asyncio.get_event_loop()

    question = await loop.run_in_executor(
        None,
        lambda: generate_question(
            body.job_title, 
            body.round_number, 
            body.history,
            body.interview_type,
            body.type_instruction,
            body.company,
            body.level
        )
    )

    await manager.send_event(current_user, {
        "agent": "Mock Interviewer",
        "status": "working",
        "message": f"Round {body.round_number} question generated",
        "timestamp": datetime.utcnow().isoformat(),
    })

    return {
        "question": question,
        "round": body.round_number,
        "round_number": body.round_number,
    }


# ── Interview — Score Answer ──────────────────────────────────────────────────
# ── Interview — Score Answer ──────────────────────────────────────────────────
@app.post("/api/interview/score-text")
async def score_interview_answer_text(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """
    Score an interview answer from text transcript.
    No audio file. No whisper. No ffmpeg. No dependencies.
    Browser handles transcription via Web Speech API.
    """
    from agents.mock_interviewer import score_answer

    transcript = request.get("transcript", "").strip()
    question   = request.get("question", "")
    job_title  = request.get("job_title", "Software Engineer")
    user_id    = request.get("user_id", "")

    effective_user = user_id or current_user

    if not transcript:
        raise HTTPException(
            status_code=400,
            detail="No transcript provided. Make sure microphone is working."
        )

    loop = asyncio.get_event_loop()
    score = await loop.run_in_executor(
        None,
        lambda: score_answer(question, transcript, job_title)
    )

    # Append to session history
    session = await get_session(effective_user) or {}
    history = session.get("interview_history") or []
    if not isinstance(history, list):
        history = []
    history.append({
        "question": question,
        "answer": transcript,
        "score": score,
    })
    await upsert_session(effective_user, interview_history=history)

    await manager.send_event(effective_user, {
        "agent": "Mock Interviewer",
        "status": "done",
        "message": f"Answer scored: {score.get('score', 0)}/10",
        "timestamp": datetime.utcnow().isoformat(),
    })

    return {
        "transcript": transcript,
        "score": score
    }


# ALSO keep old endpoint but make it text-based too (for compatibility)
@app.post("/api/interview/score")
async def score_interview_answer(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    return await score_interview_answer_text(request, current_user)


# ── Interview — Generate Follow-up ────────────────────────────────────────────
@app.post("/api/interview/followup")
async def generate_followup(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """Generate a short probing follow-up question based on the candidate's answer."""
    original_question = request.get("original_question", "")
    answer_given      = request.get("answer_given", "")
    score             = request.get("score", {})
    job_title         = request.get("job_title", "Software Engineer")

    prompt = f"""You are a senior interviewer for a {job_title} position.
The candidate just answered this question: {original_question}
Their answer was: {answer_given}
Their score was {score.get("score", 5)}/10.

Generate ONE short follow-up probing question that:
- Digs deeper into something vague or interesting in their answer
- Asks for a specific example if they were too general
- Challenges an assumption they made
- Asks what they would do differently

Examples of good follow-ups:
- "Can you give me a specific example of when you did that?"
- "What was the biggest challenge you faced in that situation?"
- "How would you approach that differently with what you know now?"
- "What metrics did you use to measure success there?"
- "What would you have done if that approach hadn't worked?"

Return ONLY the follow-up question. One sentence. No preamble.
"""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: cfg.llm_creative.invoke(prompt))
        followup_text = result.content.strip() if hasattr(result, "content") else str(result)
        followup_text = followup_text.strip().strip('"').strip("'")
    except Exception as e:
        logger.error("Follow-up generation failed: %s", e)
        followup_text = "What was the biggest challenge you faced in that situation and what did you learn?"

    return {"followup_question": followup_text}


# ── Interview — Final Assessment Report ───────────────────────────────────────
@app.post("/api/interview/report")
async def generate_interview_report(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """Review complete interview history and generate final assessment, strengths, and study topics."""
    history   = request.get("history", [])
    job_title = request.get("job_title", "Software Engineer")

    # Format history summary for the LLM
    history_summary = ""
    for idx, h in enumerate(history):
        history_summary += f"Round {idx+1}:\n"
        history_summary += f"Question: {h.get('question', '')}\n"
        history_summary += f"Answer: {h.get('answer', '')[:300]}\n"
        score_val = h.get('score', {})
        if isinstance(score_val, dict):
            history_summary += f"Scores: Overall={score_val.get('score')}, Clarity={score_val.get('clarity')}, Relevance={score_val.get('relevance')}\n"
            history_summary += f"Feedback: {score_val.get('feedback')}\n"
        else:
            history_summary += f"Score: {score_val}\n"
        history_summary += "\n"

    prompt = f"""You are a senior interviewer. Review this complete interview for a {job_title} role.

Interview history (questions, answers, and scores):
{history_summary}

Generate a final assessment in this EXACT JSON format (no markdown, no extra text):
{{
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "improvements": ["<area 1>", "<area 2>", "<area 3>"],
  "study_topics": ["<topic 1>", "<topic 2>", "<topic 3>"],
  "overall_feedback": "<2 sentence summary of the candidate's performance>",
  "hire_recommendation": "<Strong Hire|Hire|Maybe|No Hire>"
}}
"""
    try:
        from agents.mock_interviewer import _parse_json_from_llm
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: cfg.llm.invoke(prompt))
        raw_output = result.content if hasattr(result, "content") else str(result)
        report_data = _parse_json_from_llm(raw_output)
    except Exception as e:
        logger.error("Report generation failed: %s", e)
        # Fallback report if Gemini fails
        report_data = {
            "strengths": ["Clear communication style", "Solid grasp of core engineering principles", "Honest self-assessment"],
            "improvements": ["Incorporate more quantifiable metrics", "Structure technical examples more deeply", "Explore alternative trade-offs"],
            "study_topics": ["System architecture design", "Performance optimization techniques", "STAR interview methodology"],
            "overall_feedback": "The candidate demonstrated solid potential and core technical capability. Focusing on structuring answers with metrics and clear business value will yield stronger results.",
            "hire_recommendation": "Hire"
        }

    return report_data


def choose_unused_fallback(replies: list, history: list) -> str:
    import random
    if not history:
        return random.choice(replies)
    
    # Extract all assistant texts from history
    history_texts = [m.get("content", "").lower() for m in history if m.get("role") == "assistant"]
    
    for r in replies:
        # Check if the first 25 characters are already in any of the assistant messages
        r_clean = r.lower()[:25]
        is_used = False
        for h in history_texts:
            if r_clean in h:
                is_used = True
                break
        if not is_used:
            return r
            
    return random.choice(replies)


def get_smart_fallback(user_message: str, history: list, coach_name: str) -> str:
    msg = user_message.lower()
    
    # 1. Sports / Badminton / Physical Activities
    if any(k in msg for k in ["badminton", "sport", "game", "play", "football", "cricket", "tennis", "match", "gym", "exercise", "active", "workout"]):
        if "badminton" in msg:
            replies = [
                f"Oh, badminton is a fantastic sport! It requires so much agility and quick reflexes. Do you play for fun, or have you competed in any local matches?",
                "That's wonderful! Playing badminton in your hometown sounds like a great way to stay active and connected with friends. Do you prefer playing singles or doubles?",
                "Badminton is such an engaging game. How is the sports culture in your hometown? Are there good courts or clubs nearby?"
            ]
        else:
            replies = [
                "Sports are such a great way to stay active and clear your mind. What kind of sports do you enjoy playing or watching the most?",
                "I completely agree! Staying active through sports is so important. How often do you get to play or exercise during the week?",
                "That's awesome. Playing sports really helps build teamwork and focus. Have you always been into sports, or is this a recent interest?"
            ]
        return choose_unused_fallback(replies, history)
        
    # 2. Greetings / Introductions / Small Talk
    if any(k in msg for k in ["hello", "hi ", "hey", "good morning", "good afternoon", "greetings", "introduce", "who are you"]):
        replies = [
            f"Hello! I'm {coach_name}, and it's wonderful to chat with you today. What topic or hobby would you like to discuss?",
            f"Hi there! How has your day been going so far? I'm excited to practice English together.",
            f"Hey! It's great to hear from you. What's on your mind today? We can chat about sports, careers, or anything you like!"
        ]
        return choose_unused_fallback(replies, history)

    # 3. Technology / AI / Careers / Job Hunt
    if any(k in msg for k in ["tech", "ai", "artificial intelligence", "coding", "programming", "software", "job", "career", "interview", "developer", "sde"]):
        replies = [
            "The tech industry is evolving so rapidly right now, especially with AI. What specific area of technology or software engineering interests you the most?",
            "Career growth in tech is all about continuous learning. Are there any particular programming languages or frameworks you are focusing on right now?",
            "That's a very relevant topic. Navigating a career in software development can be challenging but very rewarding. What is your ultimate career goal?"
        ]
        return choose_unused_fallback(replies, history)

    # 4. Hobbies / Routine / Weekend Plans
    if any(k in msg for k in ["hobby", "hobbies", "routine", "weekend", "free time", "relax", "music", "book", "movie", "film"]):
        replies = [
            "Hobbies and routines really help us maintain a good work-life balance. How do you usually like to unwind after a busy day?",
            "That sounds like a great way to spend your free time. How long have you been interested in that hobby?",
            "I love hearing about how people spend their weekends. Do you prefer relaxing at home, or going out and exploring new places?"
        ]
        return choose_unused_fallback(replies, history)

    # 5. Travel / Culture / Food
    if any(k in msg for k in ["travel", "trip", "vacation", "culture", "food", "eat", "cooking", "restaurant", "city", "country"]):
        replies = [
            "Exploring new cultures and foods is one of the best parts of traveling. What is the most memorable place you've ever visited?",
            "Food has such a wonderful way of bringing people together. Do you enjoy cooking at home, or do you prefer dining out at restaurants?",
            "Travel really broadens our horizons. If you could board a flight to anywhere in the world tomorrow, where would you go?"
        ]
        return choose_unused_fallback(replies, history)

    # 6. Generic natural follow-ups (if no keywords match, but make them conversational, NOT robotic!)
    replies = [
        "I see exactly what you mean! That's a great way to put it. Can you tell me a bit more about what inspired you to think about that?",
        "That makes a lot of sense. How does that play a role in your day-to-day life or your future plans?",
        "Interesting! I'd love to hear more about your experience with that. What is the biggest challenge or best part about it for you?"
    ]
    return choose_unused_fallback(replies, history)


# ── Daily English Coach — Respond ─────────────────────────────────────────────
@app.post("/api/daily-coach/respond")
async def daily_coach_respond(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """
    Generate the coach's next response in the conversation.
    The coach is a warm, encouraging English coach who talks naturally about anything.
    """
    user_message = request.get("user_message", "")
    history      = request.get("history", [])
    time_left    = request.get("time_left", 600)
    coach_name   = request.get("coach_name", "Aria")

    # Build history string from the history, excluding the very last message if it's the current user message
    history_to_use = history
    if history and history[-1].get("role") == "user" and history[-1].get("content") == user_message:
        history_to_use = history[:-1]

    history_str = ""
    for m in history_to_use:
        role = m.get("role", "assistant")
        content = m.get("content", "")
        role_label = coach_name.upper() if role == "assistant" else "USER"
        history_str += f"{role_label}: {content}\n"

    prompt = f"""You are {coach_name}, a warm, encouraging, and highly professional English communication coach having a real-time spoken voice conversation with a student.

CRITICAL CONVERSATIONAL RULES:
1. DIRECTLY REACT & RESPOND: Always acknowledge, react, and respond directly to the user's specific answer. Do not ignore what they say or give a generic response.
2. STAY ON TOPIC: Stay strictly focused on the active topic of discussion (e.g., if the user wants to talk about badminton, discuss badminton, sports, playing hobbies, etc.). Ask relevant follow-up questions that dig deeper into this topic. Do not abruptly change the subject.
3. ZERO REPETITION: Review the conversation history below very carefully. You MUST NOT repeat any questions you have already asked. Do not ask questions that are very similar to previous ones. Every question must be new and move the conversation forward.
4. SPOKEN VOICE ONLY: You are speaking out loud in a phone call. Keep responses highly natural, warm, and conversational.
5. NO FORMATTING: NEVER use asterisks, bold text, markdown, bullet points, or list formatting. Write in pure spoken words only.
6. CONCISE: Keep your response short and sweet (maximum 3 sentences).
7. GRAMMAR COACHING: If the user made a minor grammar error, gently model the correct phrasing naturally in your response without lecturing them.

Conversation History so far:
{history_str}

User just said: "{user_message}"

Respond as {coach_name} now. Follow all the rules above strictly. Ensure your response is highly contextual, stays on the topic, never repeats a question, and is under 3 sentences."""

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: cfg.llm_creative.invoke(prompt))
        reply_text = result.content.strip() if hasattr(result, "content") else str(result)
        # Remove any unwanted asterisks, markdown, or braces
        reply_text = re.sub(r"[*`_\-\#]", "", reply_text).strip()
    except Exception as e:
        logger.error("Daily coach response generation failed: %s", e)
        # Call the smart, contextual rule-based fallback system
        reply_text = get_smart_fallback(user_message, history_to_use, coach_name)

    return {"reply": reply_text}


# ── Daily English Coach — Feedback ────────────────────────────────────────────
@app.post("/api/daily-coach/feedback")
async def daily_coach_feedback(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """
    Generate end-of-session English coaching feedback
    based on the full conversation transcript.
    """
    history   = request.get("history", [])
    job_title = request.get("job_title", "")

    # Extract ONLY user messages — ignore agent messages
    user_messages = [
        m.get("content", "").strip()
        for m in history
        if m.get("role") == "user" and m.get("content", "").strip()
    ]

    # COUNT real words spoken
    full_user_text = " ".join(user_messages)
    word_count     = len(full_user_text.split()) if full_user_text else 0
    message_count  = len(user_messages)

    # ── HANDLE EMPTY OR NEAR-EMPTY SESSION ───────────────────────────
    # If user barely spoke, do NOT give fake positive feedback
    if word_count < 10:
        return {
            "fluency_score":        0,
            "overall_feedback":     f"It looks like you didn't speak much during this session — only {word_count} words were detected. Make sure your microphone is working and try to speak full sentences next time.",
            "strengths":            ["You started the session — that's the first step."],
            "improvements":         [
                "Speak in full sentences — aim for at least 3-4 sentences per response.",
                "Make sure your microphone permissions are enabled in your browser.",
                "Don't be shy — Aria won't judge you. Just talk naturally."
            ],
            "vocabulary_highlights":  [],
            "grammar_notes":          "No speech detected to analyze grammar.",
            "topic_engagement":       "No engagement detected.",
            "word_count":             word_count,
            "message_count":          message_count,
            "sentences_per_response": 0,
            "avg_words_per_message":  0
        }

    if word_count < 30:
        return {
            "fluency_score":        20,
            "overall_feedback":     f"You only spoke about {word_count} words across {message_count} replies. Very short responses make it hard to practice fluency. Try to give longer, more detailed answers next time.",
            "strengths":            ["You attempted to communicate" if message_count > 1 else "You responded at least once"],
            "improvements":         [
                "Give longer answers — try to speak for at least 20-30 seconds per response.",
                "Elaborate on your points — say WHY, not just WHAT.",
                "Don't stop after one sentence — keep the conversation going."
            ],
            "vocabulary_highlights":  [],
            "grammar_notes":          "Not enough speech to detect grammar patterns.",
            "topic_engagement":       "Minimal engagement — try to open up more next session.",
            "word_count":             word_count,
            "message_count":          message_count,
            "sentences_per_response": round(word_count / max(message_count, 1) / 10, 1),
            "avg_words_per_message":  round(word_count / max(message_count, 1), 1)
        }

    # ── COMPUTE REAL METRICS BEFORE CALLING GEMINI ───────────────────
    avg_words_per_message = round(word_count / max(message_count, 1), 1)

    # Sentence count
    sentence_count = len(re.split(r'[.!?]+', full_user_text))
    sentences_per_response = round(sentence_count / max(message_count, 1), 1)

    # Filler word count
    fillers = ["um", "uh", "uhh", "umm", "like", "you know", "basically",
               "literally", "kind of", "sort of", "i mean", "right so"]
    filler_count = sum(
        len(re.findall(r'\b' + f + r'\b', full_user_text.lower()))
        for f in fillers
    )

    # Vocabulary diversity
    words = re.findall(r'\b[a-zA-Z]{4,}\b', full_user_text.lower())
    unique_words = set(words)
    vocab_diversity = round(len(unique_words) / max(len(words), 1) * 100, 1) if words else 0.0

    # Grammar red flags (simple heuristic checks)
    grammar_flags = []
    if re.search(r'\bi is\b', full_user_text.lower()):
        grammar_flags.append("'I is' — should be 'I am'")
    if re.search(r'\bhe are\b|\bshe are\b', full_user_text.lower()):
        grammar_flags.append("Subject-verb agreement: 'he/she are' → 'he/she is'")
    if re.search(r'\bdid\s+\w+ed\b', full_user_text.lower()):
        grammar_flags.append("Double past tense: 'did walked' → 'walked'")
    if re.search(r'\bmore better\b|\bmore worse\b', full_user_text.lower()):
        grammar_flags.append("Double comparative: 'more better' → 'better'")
    if re.search(r'\bwent\s+to\s+\w+ing\b', full_user_text.lower()):
        grammar_flags.append("Verb form: 'went to eating' → 'went to eat'")

    # Fluency score formula — calculated BEFORE Gemini
    base_score = 0

    # Word count component (max 30 pts)
    if word_count >= 200:
        base_score += 30
    elif word_count >= 100:
        base_score += 20
    elif word_count >= 50:
        base_score += 12
    else:
        base_score += 6

    # Vocabulary diversity (max 25 pts)
    base_score += min(25, int(vocab_diversity * 0.4))

    # Sentence length (max 20 pts) — longer avg = more fluent
    if avg_words_per_message >= 30:
        base_score += 20
    elif avg_words_per_message >= 20:
        base_score += 15
    elif avg_words_per_message >= 12:
        base_score += 10
    elif avg_words_per_message >= 6:
        base_score += 5
    else:
        base_score += 2

    # Filler word penalty (max -15 pts)
    filler_ratio = filler_count / max(word_count, 1)
    filler_penalty = min(15, int(filler_ratio * 100))
    base_score -= filler_penalty

    # Grammar penalty (max -10 pts)
    base_score -= min(10, len(grammar_flags) * 3)

    # Clamp to 0-100
    calculated_score = max(5, min(100, base_score))

    # ── CALL GEMINI WITH ACTUAL DATA ──────────────────────────────────
    from langchain_core.prompts import ChatPromptTemplate
    prompt = ChatPromptTemplate.from_template("""
You are an expert English communication coach giving feedback on a student's 10-minute speaking practice.

ACTUAL MEASURED METRICS (use these — do not guess):
- Total words spoken: {word_count}
- Number of replies: {message_count}  
- Average words per reply: {avg_words_per_message}
- Vocabulary diversity score: {vocab_diversity}% (unique words / total words)
- Filler words detected: {filler_count} times
- Grammar issues detected: {grammar_flags}
- Calculated fluency score: {calculated_score}/100

STUDENT'S ACTUAL WORDS (analyze THIS specific text):
{user_text}

AGENT'S MESSAGES FOR CONTEXT:
{agent_text}

YOUR TASK:
Give feedback based ONLY on what this specific student actually said above.
If they used short answers, say so specifically.
If they had good vocabulary, quote the actual good words they used.
If they made grammar mistakes, quote the actual mistake from their text.
Do NOT give generic feedback. Do NOT make up things they did well if they didn't.
Be honest, specific, and encouraging.

Return ONLY valid JSON — no markdown, no backticks:
{{
  "overall_feedback": "<2 specific sentences referencing actual things they said or patterns observed>",
  "strengths": [
    "<specific strength with example from their actual speech>",
    "<specific strength — ONLY include if genuinely observed>",
    "<optional third strength — omit if not genuinely observed>"
  ],
  "improvements": [
    "<specific improvement with example of what to do differently>",
    "<specific improvement>",
    "<optional third — omit if only 2 real improvements found>"
  ],
  "vocabulary_highlights": [
    "<actual good word or phrase they used — quote it exactly>",
    "<another real word they used>"
  ],
  "grammar_notes": "<specific grammar observation — quote actual mistake if found, or confirm grammar was good>",
  "topic_engagement": "<how well did they develop topics — were answers long or short, did they elaborate?>"
}}

IMPORTANT: If strengths array would be dishonest, only include 1 item.
Vocabulary highlights must be ACTUAL words from their text — never invent them.
""")

    try:
        chain = prompt | cfg.llm
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: chain.invoke({
                "word_count":            word_count,
                "message_count":         message_count,
                "avg_words_per_message": avg_words_per_message,
                "vocab_diversity":       vocab_diversity,
                "filler_count":          filler_count,
                "grammar_flags":         str(grammar_flags) if grammar_flags else "None detected",
                "calculated_score":      calculated_score,
                "user_text":             full_user_text[:2000],  # cap for token limit
                "agent_text":            " | ".join([
                    m.get("content", "")[:100]
                    for m in history
                    if m.get("role") == "assistant"
                ])[:500]
            })
        )

        import json
        cleaned = re.sub(r"```json|```", "", result.content).strip()
        parsed  = json.loads(cleaned)

        # Always use our calculated score — never let Gemini change it
        parsed["fluency_score"]          = calculated_score
        parsed["word_count"]             = word_count
        parsed["message_count"]          = message_count
        parsed["avg_words_per_message"]  = avg_words_per_message
        parsed["sentences_per_response"] = sentences_per_response
        parsed["filler_count"]           = filler_count
        parsed["vocab_diversity"]        = vocab_diversity
        parsed["grammar_flags"]          = grammar_flags

        return parsed

    except Exception as e:
        logger.error("Daily coach feedback generation failed: %s", e)
        # Even fallback uses real calculated score
        return {
            "fluency_score":           calculated_score,
            "overall_feedback":        f"You spoke {word_count} words across {message_count} replies with {avg_words_per_message} words per response on average.",
            "strengths":               ["Completed the session"],
            "improvements":            ["Try to give longer, more detailed responses"],
            "vocabulary_highlights":   [],
            "grammar_notes":           str(grammar_flags[0]) if grammar_flags else "No major grammar issues detected.",
            "topic_engagement":        f"Average response length was {avg_words_per_message} words.",
            "word_count":              word_count,
            "message_count":           message_count,
            "avg_words_per_message":   avg_words_per_message,
            "sentences_per_response":  sentences_per_response,
            "filler_count":            filler_count,
            "vocab_diversity":         vocab_diversity,
            "grammar_flags":           grammar_flags
        }


# ── Session State ─────────────────────────────────────────────────────────────
@app.get("/api/session/{user_id}")
async def get_user_session(
    user_id: str,
    current_user: str = Depends(get_current_user),
):
    """Return full session state from SQLite."""
    session = await get_session(user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


# ── Health Check ───────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "service": "CareerMind AI",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── WebSocket — Agent Stream ──────────────────────────────────────────────────
@app.websocket("/ws/agent-stream")
async def agent_stream(websocket: WebSocket, user_id: str = Query(default="")):
    """
    WebSocket endpoint for real-time agent activity streaming.
    Client should connect with: ws://localhost:8000/ws/agent-stream?user_id=xxx
    """
    effective_user = user_id or f"guest-{uuid.uuid4().hex[:8]}"
    await manager.connect(effective_user, websocket)

    # Send welcome event
    await websocket.send_json({
        "agent": "CareerMind AI",
        "status": "connected",
        "message": "Connected to agent stream. Ready to analyze your career!",
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": effective_user,
    })

    try:
        while True:
            # Keep connection alive; client can also send ping messages
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "keepalive"})
    except WebSocketDisconnect:
        manager.disconnect(effective_user, websocket)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        manager.disconnect(effective_user, websocket)
