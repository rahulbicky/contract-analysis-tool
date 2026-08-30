"""
Central factory for the chat model and embedding model.

The project runs on Groq (chat / reasoning) + a local sentence-transformers
model (embeddings), so there is no OpenAI billing anywhere. Everything else in
the codebase imports from here so the provider can be swapped in one place.

Heavy dependencies (langchain_groq, langchain_huggingface / torch) are imported
lazily inside the factory functions so that merely importing a module that uses
them does not require the full ML stack — the test suite relies on this.
"""
import os

# Chat model (Groq). Any Groq-hosted instruct model works; 70b gives the most
# reliable structured-JSON output for the triage/research parsers.
CHAT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Local embedding model (sentence-transformers, runs on-device, no API cost).
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
# Output dimension of EMBEDDING_MODEL — used to size the Qdrant collection.
# all-MiniLM-L6-v2 -> 384. Change this if you change EMBEDDING_MODEL.
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))

_embeddings = None


def get_chat_model(temperature: float = 0):
    """Return a Groq chat model. Reads GROQ_API_KEY from the environment."""
    from langchain_groq import ChatGroq
    return ChatGroq(model=CHAT_MODEL, temperature=temperature)


def get_embeddings():
    """
    Return a shared local embedding model. Loaded once (the underlying
    sentence-transformers model is heavy) and reused.
    """
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings
        _embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return _embeddings
