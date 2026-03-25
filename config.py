import os
from dotenv import load_dotenv

load_dotenv()

# 크롤링 대상
BASE_URL = "https://www.saha.go.kr"

# 크롤링할 메뉴 경로 (카테고리명: URL 경로)
TARGET_MENUS = {
    "분야별정보": "/portal/contents.do?mId=0401000000",
    "사하복지": "/portal/contents.do?mId=0501000000",
    "전자민원": "/portal/contents.do?mId=0100000000",
    "정보공개": "/portal/contents.do?mId=0300000000",
    "구민참여": "/portal/contents.do?mId=0200000000",
    "사하소개": "/portal/contents.do?mId=0600000000",
}

# 크롤러 설정
CRAWL_DELAY = 1.0          # 요청 간격 (초)
MAX_PAGES_PER_MENU = 50    # 메뉴당 최대 페이지 수
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3

# DB 설정
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "saha_db")
MYSQL_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"

CHROMA_DB_PATH = "data/chroma_db"
CHROMA_COLLECTION = "saha_admin_info"

# LLM 설정 (Google Gemini - 무료 티어)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_LLM_MODEL = "gemini-2.0-flash"
GEMINI_EMBED_MODEL = "text-embedding-004"

# 청크 설정
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
