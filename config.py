import os
from dotenv import load_dotenv

load_dotenv()

# ===== 크롤링 대상 =====
BASE_URL = "https://www.saha.go.kr"
STAFF_DIRECTORY_URL = "https://www.saha.go.kr/portal/staff/list.do?mId=0604030000"

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

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY를 .env에 설정해주세요 (세션 위조 방지)")

# ===== 관리자 API 인증 =====
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

# ===== Supabase service role 키 (관리자 작업용, RLS 우회) =====
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# ===== CORS 허용 출처 (위젯 임베딩) =====
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "https://www.saha.go.kr").split(",")
    if o.strip()
]

# ===== Rate Limiting =====
RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "10 per minute")

# ===== 대화 이력 TTL (일 단위) =====
CONVERSATION_TTL_DAYS = int(os.getenv("CONVERSATION_TTL_DAYS", "30"))

# ===== 하이브리드 검색 가중치 (벡터:BM25) =====
# 합이 1.0이 되도록 설정. 기본 0.7:0.3 (의미 검색 우선, 키워드 보조)
HYBRID_VECTOR_WEIGHT = float(os.getenv("HYBRID_VECTOR_WEIGHT", "0.7"))
HYBRID_BM25_WEIGHT = float(os.getenv("HYBRID_BM25_WEIGHT", "0.3"))
# BM25 후보 풀 크기 (벡터 검색 후 BM25로 재랭킹할 후보 수)
HYBRID_BM25_TOP_N = int(os.getenv("HYBRID_BM25_TOP_N", "30"))

# ===== 답변 신뢰도 게이트 =====
# 검색된 최상위 문서의 "원본 벡터 유사도(코사인)"가 이 임계값 미만이면
# LLM을 호출하지 않고 안전한 안내 멘트를 출력한다 (환각 방지 + API 절약).
# 주의: MiniLM 코사인 유사도는 보통 0.4~0.7 범위라 0.85 같은 값은 거의 모두 차단됨.
#       발표 자료의 "85%"는 LLM 자가점수가 아니라 이 검색 신뢰도 임계값으로 매핑됨.
CONFIDENCE_MIN_SIMILARITY = float(os.getenv("CONFIDENCE_MIN_SIMILARITY", "0.45"))
# 신뢰도 미달 시 출력할 안전 안내 멘트
LOW_CONFIDENCE_MESSAGE = os.getenv(
    "LOW_CONFIDENCE_MESSAGE",
    "죄송합니다. 문의하신 내용에 대해 정확한 정보를 찾지 못했습니다.\n\n"
    "보다 정확한 안내를 위해 사하구청 대표전화(051-220-4000) 또는 "
    "사하구청 홈페이지(https://www.saha.go.kr)를 통해 문의해 주시기 바랍니다.",
)

# ===== 파일 인제스트 (PDF/HWPX/HWP 매뉴얼 → 지식베이스) =====
# python main.py --mode ingest-files --path <폴더 또는 파일>
FILE_INGEST_DIR = os.getenv("FILE_INGEST_DIR", "data/manuals")
# 파일에서 적재한 문서에 부여할 카테고리(검색 메타데이터)
FILE_INGEST_CATEGORY = os.getenv("FILE_INGEST_CATEGORY", "첨부파일")
