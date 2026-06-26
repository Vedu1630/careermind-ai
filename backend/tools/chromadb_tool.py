"""
CareerMind AI — ChromaDB Vector Store Tool
Manages two collections:
  1. skills_kb  — indexed from data/skills_kb/*.txt
  2. resume     — indexed from uploaded PDF text
"""
import os
import glob
import logging
from typing import Optional

import chromadb
from chromadb.config import Settings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter

from config import embeddings, SKILLS_KB_DIR, CHROMA_DB_DIR

logger = logging.getLogger(__name__)

# ── Shared ChromaDB client ─────────────────────────────────────────────────────
_chroma_client: Optional[chromadb.PersistentClient] = None


def _get_client() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_DB_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
    return _chroma_client


# ── Text splitter ──────────────────────────────────────────────────────────────
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", ", ", " ", ""],
)


# ── Skills KB Vector Store ─────────────────────────────────────────────────────
class SkillsVectorStore:
    """
    Loads all *.txt files from data/skills_kb/ and indexes them into ChromaDB.
    Call `build()` once at startup. Then use `get_retriever()` for RAG.
    """

    COLLECTION_NAME = "skills_kb"

    def __init__(self):
        self._store: Optional[Chroma] = None

    def build(self) -> None:
        """Ingest all skills KB files into ChromaDB."""
        logger.info("Building SkillsVectorStore from %s", SKILLS_KB_DIR)

        client = _get_client()
        try:
            # Check if collection exists and has documents
            collection = client.get_collection(self.COLLECTION_NAME)
            if collection.count() > 0:
                logger.info(
                    "SkillsVectorStore already exists with %d documents. Skipping build.",
                    collection.count(),
                )
                self._store = Chroma(
                    collection_name=self.COLLECTION_NAME,
                    embedding_function=embeddings,
                    client=client,
                )
                return
        except Exception as e:
            # Collection doesn't exist, proceed to build
            logger.info("Skills collection not found or empty (%s), building...", e)

        txt_files = glob.glob(os.path.join(SKILLS_KB_DIR, "*.txt"))
        if not txt_files:
            logger.warning("No .txt files found in %s", SKILLS_KB_DIR)
            return

        documents = []
        metadatas = []
        for filepath in txt_files:
            domain = os.path.splitext(os.path.basename(filepath))[0]
            with open(filepath, "r", encoding="utf-8") as f:
                raw_text = f.read()
            chunks = _splitter.split_text(raw_text)
            for chunk in chunks:
                documents.append(chunk)
                metadatas.append({"domain": domain, "source": filepath})

        self._store = Chroma.from_texts(
            texts=documents,
            embedding=embeddings,
            metadatas=metadatas,
            collection_name=self.COLLECTION_NAME,
            client=client,
        )
        logger.info(
            "SkillsVectorStore built: %d chunks from %d files",
            len(documents),
            len(txt_files),
        )

    def get_retriever(self, k: int = 5):
        """Return a LangChain retriever over the skills KB."""
        if self._store is None:
            # Try to load existing collection
            self._store = Chroma(
                collection_name=self.COLLECTION_NAME,
                embedding_function=embeddings,
                client=_get_client(),
            )
        return self._store.as_retriever(search_kwargs={"k": k})


# ── Resume Vector Store ────────────────────────────────────────────────────────
class ResumeVectorStore:
    """
    Indexes resume text (extracted from PDF) into a per-session ChromaDB collection.
    Collection name: resume_{user_id}
    """

    def index_resume(self, user_id: str, resume_text: str) -> None:
        """Chunk and embed resume text for a given user."""
        collection_name = f"resume_{user_id}"
        chunks = _splitter.split_text(resume_text)
        if not chunks:
            logger.warning("No chunks generated from resume text for user %s", user_id)
            return

        Chroma.from_texts(
            texts=chunks,
            embedding=embeddings,
            metadatas=[{"user_id": user_id, "chunk_index": i} for i, _ in enumerate(chunks)],
            collection_name=collection_name,
            client=_get_client(),
        )
        logger.info("Indexed %d resume chunks for user %s", len(chunks), user_id)

    def get_retriever(self, user_id: str, k: int = 4):
        """Return a retriever over this user's indexed resume."""
        collection_name = f"resume_{user_id}"
        store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            client=_get_client(),
        )
        return store.as_retriever(search_kwargs={"k": k})


# ── Singletons ─────────────────────────────────────────────────────────────────
skills_store = SkillsVectorStore()
resume_store = ResumeVectorStore()


def get_retriever(collection: str = "skills_kb", user_id: str = ""):
    """
    Convenience function.
    collection: 'skills_kb' | 'resume'
    """
    if collection == "resume" and user_id:
        return resume_store.get_retriever(user_id)
    return skills_store.get_retriever()
