"""
CareerMind AI — Configuration
Initializes LLM, embeddings, and environment variables.
"""
import os
os.environ["GRPC_DNS_RESOLVER"] = "native"

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv
import os
from pathlib import Path

# Load env file relative to config.py location
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# ── LLM ──────────────────────────────────────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.3,
    convert_system_message_to_human=True,
    max_retries=0,
)

# Creative LLM for natural, conversational, and highly engaging responses (temperature=0.7)
llm_creative = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.7,
    convert_system_message_to_human=True,
    max_retries=0,
)

# ── Embeddings ────────────────────────────────────────────────────────────────
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    max_retries=0,
)

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
