"""
CareerMind AI — Configuration
Initializes LLM, embeddings, and environment variables.
"""
import os
os.environ["GRPC_DNS_RESOLVER"] = "native"

from dotenv import load_dotenv
from pathlib import Path
import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_groq import ChatGroq

# Load env file relative to config.py location
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Configure Gemini
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# Gemini quota/rate-limit error keywords to detect
GEMINI_QUOTA_ERRORS = (
    "quota",
    "rate limit",
    "429",
    "resource exhausted",
    "quota exceeded",
    "too many requests",
)

def is_gemini_quota_error(error: Exception) -> bool:
    """Return True if the error is a Gemini quota/rate-limit error."""
    msg = str(error).lower()
    return any(keyword in msg for keyword in GEMINI_QUOTA_ERRORS)

# Primary: Gemini LLM
def get_gemini_llm(temperature: float = 0.7, max_tokens: int = None):
    if not GOOGLE_API_KEY:
        return None
    kwargs = {
        "model": "gemini-1.5-flash",
        "google_api_key": GOOGLE_API_KEY,
        "temperature": temperature,
        "convert_system_message_to_human": True,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatGoogleGenerativeAI(**kwargs)

# Fallback: Groq LLM
def get_groq_llm(temperature: float = 0.7, max_tokens: int = None):
    if not GROQ_API_KEY:
        return None
    kwargs = {
        "model": "llama-3.3-70b-versatile",
        "groq_api_key": GROQ_API_KEY,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatGroq(**kwargs)

# Smart LLM: tries Gemini first, falls back to Groq
class SmartLLM:
    """
    A wrapper that calls Gemini first. If Gemini raises a quota/rate-limit
    error, it automatically retries with Groq.
    """
    def __init__(self, temperature: float = 0.7, max_tokens: int = None):
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._gemini = get_gemini_llm(temperature, max_tokens)
        self._groq = get_groq_llm(temperature, max_tokens)
        self.active_provider = "gemini" if self._gemini else "groq"

    def invoke(self, messages, **kwargs):
        # Try Gemini first
        if self._gemini:
            try:
                result = self._gemini.invoke(messages, **kwargs)
                self.active_provider = "gemini"
                return result
            except Exception as e:
                if is_gemini_quota_error(e):
                    print(f"[SmartLLM] Gemini quota exceeded, switching to Groq. Error: {e}")
                    if self._groq:
                        self.active_provider = "groq"
                        return self._groq.invoke(messages, **kwargs)
                    else:
                        raise RuntimeError(
                            "Gemini quota exceeded and no GROQ_API_KEY configured. "
                            "Add GROQ_API_KEY to your .env file."
                        ) from e
                raise  # re-raise non-quota errors

        # Gemini not configured, use Groq directly
        if self._groq:
            self.active_provider = "groq"
            return self._groq.invoke(messages, **kwargs)

        raise RuntimeError(
            "No LLM configured. Set GOOGLE_API_KEY or GROQ_API_KEY in .env"
        )

    async def ainvoke(self, messages, **kwargs):
        # Async version — try Gemini, fall back to Groq
        if self._gemini:
            try:
                result = await self._gemini.ainvoke(messages, **kwargs)
                self.active_provider = "gemini"
                return result
            except Exception as e:
                if is_gemini_quota_error(e):
                    print(f"[SmartLLM] Gemini quota exceeded (async), switching to Groq.")
                    if self._groq:
                        self.active_provider = "groq"
                        return await self._groq.ainvoke(messages, **kwargs)
                    else:
                        raise RuntimeError("Gemini quota exceeded and no GROQ_API_KEY set.") from e
                raise

        if self._groq:
            self.active_provider = "groq"
            return await self._groq.ainvoke(messages, **kwargs)

        raise RuntimeError("No LLM configured.")

    # Support | piping (LangChain chains: llm | parser)
    def __or__(self, other):
        from langchain_core.runnables import RunnableLambda
        import asyncio

        def sync_invoke(messages):
            return self.invoke(messages)

        return RunnableLambda(sync_invoke) | other


# Embeddings — keep Gemini (no quota concern for embeddings in typical use)
def get_embeddings():
    if GOOGLE_API_KEY:
        return GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=GOOGLE_API_KEY,
        )
    raise RuntimeError("GOOGLE_API_KEY required for embeddings (ChromaDB RAG).")

# Convenience singletons
smart_llm = SmartLLM(temperature=0.7)
embeddings = get_embeddings()

# Legacy aliases so existing agent imports don't break
llm = smart_llm
llm_creative = smart_llm

# ── LangSmith tracing (auto-enabled via env vars) ────────────────────────────
LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "careermind-ai")

# ── External API keys ─────────────────────────────────────────────────────────
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

# ── App secrets ───────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-dev-secret-key-32chars!!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "data", "uploads")
SKILLS_KB_DIR = os.path.join(BASE_DIR, "data", "skills_kb")
CHROMA_DB_DIR = os.path.join(BASE_DIR, "data", "chroma_db")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(CHROMA_DB_DIR, exist_ok=True)
