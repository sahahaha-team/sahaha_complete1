"""
사하구청 AI 상담사 - FastAPI 웹 애플리케이션
- Flask에서 마이그레이션 (동일 엔드포인트, 동일 동작)
- ASGI 기반 비동기 친화적 구조
- 동기 LLM/DB 호출은 starlette run_in_threadpool로 워커 스레드 위임하여 이벤트 루프 비차단
"""

import uuid
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import (
    SECRET_KEY,
    FLASK_HOST,
    FLASK_PORT,
    ADMIN_API_KEY,
    CORS_ALLOWED_ORIGINS,
    RATE_LIMIT_CHAT,
)
from chatbot.ollama_runtime import get_ollama_status
from chatbot.contact_directory import contact_responder
from chatbot.emergency_guidance import answer_emergency_question

logger = logging.getLogger(__name__)


# ===== Pydantic 스키마 =====

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)


class Attachment(BaseModel):
    name: str = "첨부파일"
    url: str


class Source(BaseModel):
    title: str
    url: str
    category: str = ""
    service_type: str = "기타"
    department: str = ""  # 담당 부서명 (LLM 태깅, 본문 미명시 시 빈 문자열)
    contact: str = ""     # 담당부서 연락처 (직통번호 없으면 대표전화 폴백)
    attachments: list[Attachment] = Field(default_factory=list)  # 게시물 첨부파일(PDF/HWP 등) 다운로드 링크
    source_type: str = "official_page"
    issued_at: str = ""
    data_period: str = ""
    page_number: int = 0
    checked_at: str = ""


class Evidence(BaseModel):
    status: str = "unavailable"
    label: str = "근거 상태를 확인할 수 없음"
    official_source_count: int = 0


class ChatResponse(BaseModel):
    answer: str
    answer_details: str = ""
    sources: list[Source] = Field(default_factory=list)
    is_clarification: bool
    # 검색/태깅/LLM 단계의 부분 실패 신호. True면 프론트가 안내 배너 표시.
    degraded: bool = False
    degraded_reason: Optional[str] = None
    evidence: Evidence = Field(default_factory=Evidence)
    suggested_questions: list[str] = Field(default_factory=list)


class ClearResponse(BaseModel):
    status: str = "ok"


# ===== 싱글턴 (지연 초기화) =====

_chatbot = None
_db = None
_vector_store = None


def get_chatbot():
    global _chatbot
    if _chatbot is None:
        from chatbot.conversation import ChatBot
        _chatbot = ChatBot()
    return _chatbot


def get_db():
    global _db
    if _db is None:
        from database_db.database import Database
        _db = Database()
    return _db


def get_vector_store():
    global _vector_store
    if _vector_store is None:
        bot = get_chatbot()
        _vector_store = bot.retriever.vs
    return _vector_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 lifecycle hook"""
    logger.info("=== 사하구청 AI 상담사 웹 서버 시작 ===")
    logger.info("챗봇 사전 초기화 중 (임베딩/BM25 모델 로딩)...")
    ollama = await run_in_threadpool(get_ollama_status)
    if ollama["model_ready"]:
        logger.info(f"Ollama 준비 완료: {ollama['model']}")
    else:
        logger.warning(ollama["message"])
    try:
        await run_in_threadpool(get_chatbot)
        logger.info("챗봇 사전 초기화 완료")
    except Exception as e:
        logger.warning(f"챗봇 사전 초기화 실패 (첫 요청 시 재시도): {e}")

    yield


# ===== FastAPI 앱 =====

limiter = Limiter(key_func=get_remote_address, default_limits=["200 per hour"])

app = FastAPI(
    title="사하구청 AI 상담사",
    description="부산광역시 사하구청 RAG 기반 AI 상담사",
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 세션 (Flask session 대체 - itsdangerous 기반 서명 쿠키)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")

# CORS (위젯 임베딩 출처 제한)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Server-Timing"],
)

# 정적 파일 / 템플릿 (Flask와 동일 경로)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ===== 보안 헤더 미들웨어 =====

@app.middleware("http")
async def security_headers(request: Request, call_next):
    """클릭재킹/XSS 방지 보안 헤더 부착"""
    started = time.perf_counter()
    response = await call_next(request)
    allowed = " ".join(CORS_ALLOWED_ORIGINS) if CORS_ALLOWED_ORIGINS else "'self'"
    # 공식 홈페이지에 삽입되는 위젯은 CSP frame-ancestors로 허용 출처를 제한한다.
    # SAMEORIGIN을 함께 보내면 브라우저가 saha.go.kr의 iframe까지 차단할 수 있다.
    if request.url.path != "/widget":
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        f"frame-ancestors 'self' {allowed}; "
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self'"
    )
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
    return response


# ===== 관리자 인증 의존성 =====

async def require_admin(x_admin_key: Optional[str] = Header(default=None)):
    """관리자 API Key 검증"""
    if not ADMIN_API_KEY:
        logger.warning("ADMIN_API_KEY 미설정 - 관리자 엔드포인트 비활성화")
        raise HTTPException(status_code=503, detail="관리자 기능이 비활성화되어 있습니다")
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    return True


# ===== 라우트 =====

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """메인 챗봇 페이지"""
    if "session_id" not in request.session:
        request.session["session_id"] = str(uuid.uuid4())
    return templates.TemplateResponse(request, "index.html")


@app.get("/widget", response_class=HTMLResponse)
async def widget(request: Request):
    """홈페이지 임베딩용 위젯 (iframe)"""
    if "session_id" not in request.session:
        request.session["session_id"] = str(uuid.uuid4())
    return templates.TemplateResponse(request, "widget.html")


@app.get("/system", response_class=HTMLResponse)
async def system_dashboard(request: Request):
    """발표·운영 점검용 비민감 시스템 상태 화면."""
    return templates.TemplateResponse(request, "system.html")


@app.get("/api/health")
async def health():
    """웹·Ollama 준비 상태를 운영 점검용으로 제공한다."""
    ollama = await run_in_threadpool(get_ollama_status)
    return {
        "status": "ok" if ollama["model_ready"] else "degraded",
        "llm_provider": "ollama",
        "ollama": ollama,
    }


@app.get("/api/system-status")
async def system_status():
    """콘텐츠를 노출하지 않고 구성요소별 상태와 건수만 반환한다."""
    ollama = await run_in_threadpool(get_ollama_status)
    try:
        db = get_db()
        vs = get_vector_store()
        vector_stats = await run_in_threadpool(vs.collection_stats)
        queue_stats = await run_in_threadpool(db.ingestion_queue_stats)
        latest_crawl = await run_in_threadpool(db.latest_crawl_run)
        search_ready = vector_stats.get("total_vectors", 0) > 0
    except Exception as exc:
        logger.warning(f"시스템 상태 DB 점검 실패: {exc}")
        vector_stats = {"total_vectors": 0}
        queue_stats = {"available": False, "queued": 0, "running": 0, "succeeded": 0, "failed": 0}
        latest_crawl = None
        search_ready = False
    return {
        "status": "ok" if ollama["model_ready"] and search_ready and queue_stats["available"] else "degraded",
        "web": {"ready": True},
        "ollama": ollama,
        "search": {"ready": search_ready, **vector_stats},
        "queue": queue_stats,
        "latest_crawl": latest_crawl,
        "privacy": {"conversation_persistence": False},
    }


@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT_CHAT)
async def chat(request: Request, payload: ChatRequest):
    """챗봇 대화 API"""
    user_message = payload.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="빈 메시지입니다")

    session_id = request.session.get("session_id") or str(uuid.uuid4())
    request.session["session_id"] = session_id

    try:
        emergency_result = answer_emergency_question(user_message)
        if emergency_result is not None:
            if _chatbot is not None:
                _chatbot._clear_pending_clarification(session_id)
            return ChatResponse(**emergency_result)
        # The local contact file is consulted before accessing models or DB.
        contact_query = _chatbot.contextual_message(session_id, user_message) if _chatbot is not None else user_message
        contact_result = await run_in_threadpool(contact_responder.respond, session_id, contact_query)
        if contact_result is not None:
            if _chatbot is not None:
                _chatbot.remember_contact_exchange(session_id, user_message, contact_result)
            return ChatResponse(**contact_result)
        bot = get_chatbot()
        # 동기 LLM 호출은 워커 스레드로 위임 (이벤트 루프 비차단)
        result = await run_in_threadpool(bot.chat, session_id, user_message)
        contact_responder.observe(session_id, user_message)
        return ChatResponse(**result)
    except Exception as e:
        logger.error(f"챗봇 오류: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "answer": "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                "sources": [],
                "is_clarification": False,
                "degraded": True,
                "degraded_reason": "internal_error",
                "evidence": {
                    "status": "unavailable",
                    "label": "서비스 연결을 확인할 수 없음",
                    "official_source_count": 0,
                },
                "suggested_questions": [],
            },
        )


@app.post("/api/clear", response_model=ClearResponse)
async def clear_chat(request: Request):
    """대화 초기화 API"""
    session_id = request.session.get("session_id")
    if session_id:
        contact_responder.clear(session_id)
        try:
            if _chatbot is not None:
                await run_in_threadpool(_chatbot.clear_session, session_id)
        except Exception as e:
            logger.error(f"대화 초기화 오류: {e}")

    request.session["session_id"] = str(uuid.uuid4())
    return ClearResponse()


@app.get("/api/stats")
@limiter.limit("30 per minute")
async def stats(request: Request, _auth: bool = Depends(require_admin)):
    """시스템 통계 API (관리자 전용)"""
    try:
        db = get_db()
        vs = get_vector_store()
        db_stats = await run_in_threadpool(db.stats)
        vs_stats = await run_in_threadpool(vs.collection_stats)
        return {**db_stats, **vs_stats}
    except Exception as e:
        logger.error(f"/api/stats 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="시스템 오류가 발생했습니다")


# ===== 실행 진입점 =====

def run_server():
    """uvicorn으로 FastAPI 서버 기동"""
    import uvicorn
    uvicorn.run(
        "app:app",
        host=FLASK_HOST,
        port=FLASK_PORT,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    run_server()
