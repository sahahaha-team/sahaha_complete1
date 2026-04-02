import os
from dotenv import load_dotenv

load_dotenv()

# ===== 크롤링 대상 =====
BASE_URL = "https://www.saha.go.kr"

TARGET_MENUS = {
    "분야별정보": "/portal/contents.do?mId=0401000000",
    "사하복지": "/portal/contents.do?mId=0501000000",
    "전자민원": "/portal/contents.do?mId=0100000000",
    "정보공개": "/portal/contents.do?mId=0300000000",
    "구민참여": "/portal/contents.do?mId=0200000000",
    "사하소개": "/portal/contents.do?mId=0600000000",
}

# ===== 크롤러 설정 =====
CRAWL_DELAY = 1.0
MAX_PAGES_PER_MENU = 50
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3

# ===== Supabase 설정 (PostgreSQL + pgvector) =====
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")  # anon/public key

# ===== LLM 설정 (Groq - 무료 티어) =====
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_LLM_MODEL = "llama-3.3-70b-versatile"

# ===== 청크 설정 =====
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# ===== 챗봇 설정 =====
MAX_CONVERSATION_HISTORY = 10
MAX_RETRIEVAL_RESULTS = 5
CHATBOT_TEMPERATURE = 0.3

# ===== Flask 설정 =====
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "saha-chatbot-secret-key-change-in-production")
