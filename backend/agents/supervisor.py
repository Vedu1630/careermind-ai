"""
CareerMind AI — LangGraph Supervisor
Orchestrates all agents using a StateGraph. Supports streaming events via callback.
LangSmith tracing is enabled automatically when LANGCHAIN_TRACING_V2=true.
"""
import asyncio
import logging
import operator
from typing import Annotated, Callable, Dict, List, TypedDict

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


# ── Agent State ────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    user_id: str
    resume_path: str
    resume_text: str
    resume_analysis: dict
    job_query: str
    job_location: str
    job_listings: list
    selected_job: dict
    rewritten_resume: dict
    interview_history: list
    interview_score: dict
    current_step: str
    events: Annotated[List[str], operator.add]


# ── Event broadcasting ─────────────────────────────────────────────────────────
_event_callbacks: Dict[str, List[Callable]] = {}


def register_event_callback(user_id: str, callback: Callable) -> None:
    """Register a callback to receive events for a user session."""
    if user_id not in _event_callbacks:
        _event_callbacks[user_id] = []
    _event_callbacks[user_id].append(callback)


def unregister_event_callback(user_id: str, callback: Callable) -> None:
    """Remove a callback."""
    if user_id in _event_callbacks:
        try:
            _event_callbacks[user_id].remove(callback)
        except ValueError:
            pass


def _emit(user_id: str, agent: str, status: str, message: str) -> None:
    """Emit an event to all registered callbacks for a user."""
    event = {
        "agent": agent,
        "status": status,
        "message": message,
    }
    callbacks = _event_callbacks.get(user_id, [])
    for cb in callbacks:
        try:
            cb(event)
        except Exception as e:
            logger.error("Event callback error: %s", e)


# ── Node implementations ───────────────────────────────────────────────────────
async def resume_analyzer_node(state: AgentState) -> AgentState:
    """Extract and analyze resume."""
    from agents.resume_analyzer import analyze_resume

    user_id = state.get("user_id", "anonymous")
    _emit(user_id, "Resume Analyzer", "thinking", "Starting resume analysis...")

    def progress_cb(msg: str):
        _emit(user_id, "Resume Analyzer", "working", msg)

    analysis = await analyze_resume(
        state["resume_path"],
        user_id=user_id,
        progress_callback=progress_cb,
    )

    _emit(user_id, "Resume Analyzer", "done",
          f"Analysis complete! Score: {analysis.get('overall_score', 0)}/100")

    return {
        **state,
        "resume_text": analysis.get("resume_text", ""),
        "resume_analysis": analysis,
        "current_step": "resume_analyzed",
        "events": [f"Resume analyzed — score: {analysis.get('overall_score', 0)}/100"],
    }


async def job_scraper_node(state: AgentState) -> AgentState:
    """Fetch and score job listings."""
    from agents.job_scraper import scrape_and_score

    user_id = state.get("user_id", "anonymous")
    _emit(user_id, "Job Scraper", "thinking", "Searching for matching jobs...")

    def progress_cb(msg: str):
        _emit(user_id, "Job Scraper", "working", msg)

    jobs = await scrape_and_score(
        query=state.get("job_query", "Software Engineer"),
        location=state.get("job_location", "United States"),
        resume_analysis=state.get("resume_analysis", {}),
        progress_callback=progress_cb,
    )

    _emit(user_id, "Job Scraper", "done", f"Found {len(jobs)} matched jobs!")

    return {
        **state,
        "job_listings": jobs,
        "current_step": "jobs_scraped",
        "events": [f"Scraped {len(jobs)} jobs — top match: {jobs[0]['match_score']}%" if jobs else "No jobs found"],
    }


async def resume_rewriter_node(state: AgentState) -> AgentState:
    """Rewrite resume for selected job."""
    from agents.resume_rewriter import rewrite_resume

    user_id = state.get("user_id", "anonymous")
    selected_job = state.get("selected_job", {})

    if not selected_job:
        _emit(user_id, "Resume Rewriter", "error", "No job selected for rewrite.")
        return {**state, "current_step": "rewrite_skipped"}

    _emit(user_id, "Resume Rewriter", "thinking",
          f"Rewriting resume for {selected_job.get('title', 'selected role')}...")

    def progress_cb(msg: str):
        _emit(user_id, "Resume Rewriter", "working", msg)

    # Call the async rewrite_resume function directly
    rewritten = await rewrite_resume(
        state.get("resume_path", ""),
        selected_job,
        progress_callback=progress_cb,
    )

    changes = len(rewritten.get("changes_summary", []))
    _emit(user_id, "Resume Rewriter", "done", f"Resume rewritten! {changes} improvements made.")

    return {
        **state,
        "rewritten_resume": rewritten,
        "current_step": "resume_rewritten",
        "events": [f"Resume rewritten with {changes} changes"],
    }


async def mock_interviewer_node(state: AgentState) -> AgentState:
    """Generate interview question and score."""
    from agents.mock_interviewer import generate_question

    user_id = state.get("user_id", "anonymous")
    selected_job = state.get("selected_job", {})
    job_title = selected_job.get("title", "Software Engineer") if selected_job else "Software Engineer"
    history = state.get("interview_history", [])
    round_number = len(history) + 1

    _emit(user_id, "Mock Interviewer", "thinking",
          f"Generating round {round_number} interview question...")

    # Run in thread pool
    loop = asyncio.get_event_loop()
    question = await loop.run_in_executor(
        None,
        lambda: generate_question(job_title, round_number, history)
    )

    _emit(user_id, "Mock Interviewer", "done", f"Question ready: {question[:80]}...")

    return {
        **state,
        "current_step": "interview_question_ready",
        "events": [f"Interview question {round_number} generated"],
    }


# ── Routing logic ──────────────────────────────────────────────────────────────
def route_from_supervisor(state: AgentState) -> str:
    """Conditional routing based on current_step."""
    step = state.get("current_step", "idle")

    routing = {
        "idle": "resume_analyzer",
        "resume_analyzed": "job_scraper",
        "jobs_scraped": "resume_rewriter",
        "resume_rewritten": "mock_interviewer",
        "interview_question_ready": END,
        "rewrite_skipped": END,
    }
    return routing.get(step, END)


# ── Build the LangGraph ────────────────────────────────────────────────────────
def build_graph() -> StateGraph:
    """Build and compile the CareerMind AI agent graph."""
    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("resume_analyzer", resume_analyzer_node)
    builder.add_node("job_scraper", job_scraper_node)
    builder.add_node("resume_rewriter", resume_rewriter_node)
    builder.add_node("mock_interviewer", mock_interviewer_node)

    # Entry point
    builder.set_entry_point("resume_analyzer")

    # Edges
    builder.add_edge("resume_analyzer", "job_scraper")
    builder.add_edge("job_scraper", "resume_rewriter")
    builder.add_edge("resume_rewriter", "mock_interviewer")
    builder.add_edge("mock_interviewer", END)

    return builder.compile()


# ── Singleton compiled graph ───────────────────────────────────────────────────
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_full_pipeline(
    user_id: str,
    resume_path: str,
    job_query: str = "Software Engineer",
    job_location: str = "United States",
) -> AgentState:
    """
    Run the complete CareerMind AI pipeline for a user.
    Returns final state after all agents complete.
    """
    initial_state: AgentState = {
        "user_id": user_id,
        "resume_path": resume_path,
        "resume_text": "",
        "resume_analysis": {},
        "job_query": job_query,
        "job_location": job_location,
        "job_listings": [],
        "selected_job": {},
        "rewritten_resume": {},
        "interview_history": [],
        "interview_score": {},
        "current_step": "idle",
        "events": [],
    }

    graph = get_graph()
    final_state = await graph.ainvoke(initial_state)
    return final_state
