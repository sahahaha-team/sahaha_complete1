"""
사하구청 AI 상담사 - FastAPI 웹 애플리케이션
- Flask에서 마이그레이션 (동일 엔드포인트, 동일 동작)
- ASGI 기반 비동기 친화적 구조
- 동기 LLM/DB 호출은 starlette run_in_threadpool로 워커 스레드 위임하여 이벤트 루프 비차단
"""

import uuid
import logging
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

logger = logging.getLogger(__name__)


# ===== Pydantic 스키마 =====

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)


class Source(BaseModel):
    title: str
    url: str
    category: str = ""
    service_type: str = "기타"


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    is_clarification: bool
    # 검색/태깅/LLM 단계의 부분 실패 신호. True면 프론트가 안내 배너 표시.
    degraded: bool = False
    degraded_reason: Optional[str] = None


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


# ===== APScheduler (lifespan에서 시작/종료) =====

_scheduler = None


def _init_scheduler():
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from config import CONVERSATION_TTL_DAYS

    # 순환 import 방지를 위해 main.py의 job 함수는 lazy import
    from main import run_incremental, cleanup_old_conversations_job

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        func=run_incremental, trigger="cron", hour=3, minute=0,
        id="incremental_crawl", misfire_grace_time=3600,
    )
    _scheduler.add_job(
        func=cleanup_old_conversations_job, trigger="cron", hour=4, minute=0,
        id="conversation_ttl_cleanup", misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(
        f"=== 스케줄러 등록 (증분 크롤링 03:00 / 대화 이력 {CONVERSATION_TTL_DAYS}일 정리 04:00) ==="
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 lifecycle hook"""
    logger.info("=== 사하구청 AI 상담사 웹 서버 시작 ===")
    logger.info("챗봇 사전 초기화 중 (임베딩/NER/BM25 모델 로딩)...")
    try:
        await run_in_threadpool(get_chatbot)
        logger.info("챗봇 사전 초기화 완료")
    except Exception as e:
        logger.warning(f"챗봇 사전 초기화 실패 (첫 요청 시 재시도): {e}")

    try:
        _init_scheduler()
    except Exception as e:
        logger.error(f"스케줄러 초기화 실패: {e}")

    yield

    # shutdown
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("스케줄러 종료")
        except Exception as e:
            logger.warning(f"스케줄러 종료 실패: {e}")


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
)

# 정적 파일 / 템플릿 (Flask와 동일 경로)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ===== 보안 헤더 미들웨어 =====

@app.middleware("http")
async def security_headers(request: Request, call_next):
    """클릭재킹/XSS 방지 보안 헤더 부착"""
    response = await call_next(request)
    allowed = " ".join(CORS_ALLOWED_ORIGINS) if CORS_ALLOWED_ORIGINS else "'self'"
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
        bot = get_chatbot()
        # 동기 LLM 호출은 워커 스레드로 위임 (이벤트 루프 비차단)
        result = await run_in_threadpool(bot.chat, session_id, user_message)
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
            },
        )


@app.post("/api/clear", response_model=ClearResponse)
async def clear_chat(request: Request):
    """대화 초기화 API"""
    session_id = request.session.get("session_id")
    if session_id:
        try:
            bot = get_chatbot()
            await run_in_threadpool(bot.clear_session, session_id)
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
