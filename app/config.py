# app/config.py
import os
from dotenv import load_dotenv
load_dotenv()

DB_DSN = os.getenv("DATABASE_URL") or "postgresql://qwerty:qwerty@77.37.96.71:5432/archive_db"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
