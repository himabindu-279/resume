import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "database.db"))
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "secret123")

OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TIMEOUT_SECONDS = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
CHAT_HISTORY_WINDOW = int(os.getenv("CHAT_HISTORY_WINDOW", "10"))