"""
CareerMind AI — Configuration
Initializes Groq-only configuration.
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Load env file relative to config.py location
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

class SmartLLM:
    """
    A lightweight Groq-only SmartLLM mock class to prevent import issues.
    """
    def __init__(self, temperature: float = 0.7, max_tokens: int = None):
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.active_provider = "groq"

    def invoke(self, messages, **kwargs):
        from main import call_groq
        prompt = messages
        if isinstance(messages, list):
            prompt = "\n".join(m.get("content", "") for m in messages if isinstance(m, dict))
        res = call_groq(prompt, temperature=self.temperature, max_tokens=self.max_tokens or 1000)
        return type('Response', (object,), {'content': res})

    async def ainvoke(self, messages, **kwargs):
        from main import call_groq_async
        prompt = messages
        if isinstance(messages, list):
            prompt = "\n".join(m.get("content", "") for m in messages if isinstance(m, dict))
        res = await call_groq_async(prompt, temperature=self.temperature, max_tokens=self.max_tokens or 1000)
        return type('Response', (object,), {'content': res})

    def __or__(self, other):
        return self

smart_llm = SmartLLM(temperature=0.7)
llm = smart_llm
llm_creative = smart_llm

def get_embeddings():
    return None

# Tracing & keys
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-dev-secret-key-32chars!!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "data", "uploads")
SKILLS_KB_DIR = os.path.join(BASE_DIR, "data", "skills_kb")
CHROMA_DB_DIR = os.path.join(BASE_DIR, "data", "chroma_db")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(CHROMA_DB_DIR, exist_ok=True)
