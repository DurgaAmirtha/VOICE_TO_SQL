import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present (for local testing)
load_dotenv()

class Config:
    # Base Path
    BASE_DIR = Path(__file__).resolve().parent
    
    # Resolve API keys: check streamlit secrets first, then environment / .env
    GEMINI_API_KEY = None
    OPENAI_API_KEY = None
    GROQ_API_KEY = None
    
    try:
        import streamlit as st
        # If running within a streamlit context, try reading st.secrets
        if hasattr(st, "secrets"):
            if "GEMINI_API_KEY" in st.secrets:
                GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
            if "OPENAI_API_KEY" in st.secrets:
                OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
            if "GROQ_API_KEY" in st.secrets:
                GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    except Exception:
        # Ignore errors if streamlit is not running (e.g. running raw command line script)
        pass

    # Fallback to environment variables
    if not GEMINI_API_KEY:
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not OPENAI_API_KEY:
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not GROQ_API_KEY:
        GROQ_API_KEY = os.getenv("GROQ_API_KEY")
        
    # Folders
    DATABASE_DIR = BASE_DIR / "database"
    UPLOADS_DIR = BASE_DIR / "uploads"
    CHROMA_DIR = BASE_DIR / "chroma_db"
    LOGS_DIR = BASE_DIR / "logs"
    
    # Ensure folders exist
    for folder in [DATABASE_DIR, UPLOADS_DIR, CHROMA_DIR, LOGS_DIR]:
        folder.mkdir(parents=True, exist_ok=True)
        
    # Database Paths
    DEMO_DB_PATH = DATABASE_DIR / "demo_business.db"
    
    # LLM Settings
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    # Query Validation Settings
    MAX_ROW_LIMIT = int(os.getenv("MAX_ROW_LIMIT", "100"))
    
    # RAG Settings
    EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
    CHROMA_SCHEMA_COLLECTION = "database_schema_metadata"
    
    # Log File Path
    LOG_FILE_PATH = LOGS_DIR / "app.log"
