# backend/core/singletons.py
import os
import logging
from dotenv import load_dotenv

# Try importing whisper
try:
    import whisper
    _whisper_installed = True
except ImportError:
    _whisper_installed = False

import chromadb
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
import httpx
from config import CHROMA_DB_DIR, SKILLS_KB_DIR

load_dotenv()

logger = logging.getLogger(__name__)

print("⚡ Initializing singletons...")

# ── LLM (one instance, reused everywhere) ─────────────────────────
_llm_fast = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.1,          # lower = faster, more deterministic
    max_tokens=800,           # cap output tokens for speed
    convert_system_message_to_human=True,
)

_llm_quality = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.3,
    max_tokens=2000,          # for rewriting tasks that need more output
    convert_system_message_to_human=True,
)

_embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

# ── Whisper (loaded once, NEVER again) ────────────────────────────
_whisper_model = None
if _whisper_installed:
    print("⚡ Loading Whisper model...")
    try:
        _whisper_model = whisper.load_model("base")  # base = best speed/accuracy tradeoff
        print("✅ Whisper ready")
    except Exception as e:
        print(f"⚠️ Whisper load failed: {e}")
else:
    print("⚠️ Whisper package not installed, using SpeechRecognition fallback")

# ── ChromaDB (one client, one collection, indexed) ────────────────
_chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)

_skills_vectorstore = None

def _init_skills_vectorstore():
    global _skills_vectorstore
    if _skills_vectorstore is not None:
        return _skills_vectorstore

    print("⚡ Building skills vectorstore...")
    try:
        # Try loading existing
        _skills_vectorstore = Chroma(
            collection_name="skills_kb",
            embedding_function=_embeddings,
            client=_chroma_client,
        )
        count = _skills_vectorstore._collection.count()
        if count > 0:
            print(f"✅ Skills vectorstore loaded ({count} chunks)")
            return _skills_vectorstore
    except Exception as e:
        print(f"Skills vectorstore load failed, attempting build: {e}")

    # Build from scratch
    try:
        loader = DirectoryLoader(SKILLS_KB_DIR, loader_cls=TextLoader, glob="*.txt")
        docs = loader.load()
    except Exception as e:
        print(f"DirectoryLoader failed: {e}, falling back to manual text loading")
        from langchain.schema import Document
        docs = []
        import glob
        for filepath in glob.glob(os.path.join(SKILLS_KB_DIR, "*.txt")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    docs.append(Document(page_content=f.read(), metadata={"source": filepath}))
            except Exception:
                pass

    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=40)
    chunks = splitter.split_documents(docs)
    _skills_vectorstore = Chroma.from_documents(
        chunks,
        _embeddings,
        collection_name="skills_kb",
        client=_chroma_client,
    )
    print(f"✅ Skills vectorstore built ({len(chunks)} chunks)")
    return _skills_vectorstore

# ── HTTP client with connection pooling (for job APIs) ────────────
_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(8.0, connect=3.0),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)

# ── In-memory cache for repeated requests ─────────────────────────
_cache: dict = {}

# ── Public accessors ──────────────────────────────────────────────
def get_llm(quality: bool = False):
    return _llm_quality if quality else _llm_fast

def get_embeddings():
    return _embeddings

def get_whisper():
    return _whisper_model

def get_skills_retriever(k: int = 4):
    vs = _init_skills_vectorstore()
    return vs.as_retriever(search_kwargs={"k": k})

def get_http_client():
    return _http_client

def get_cache():
    return _cache
