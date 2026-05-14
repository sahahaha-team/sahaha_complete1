"""
사하구청 AI 상담사 - Flask 웹 애플리케이션
"""

import uuid
import logging
from functools import wraps
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import (
    SECRET_KEY,
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    ADMIN_API_KEY,
    CORS_ALLOWED_ORIGINS,
    RATE_LIMIT_CHAT,
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 위젯 임베딩 시 명시된 출처만 허용 (클릭재킹 방지)
CORS(app, resources={r"/api/*": {"origins": CORS_ALLOWED_ORIGINS}}, supports_credentials=True)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per hour"],
)


@app.after_request
def apply_security_headers(response):
    """클릭재킹/XSS 방지 보안 헤더"""
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


def require_admin(fn):
    """관리자 API Key 인증 데코레이터"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not ADMIN_API_KEY:
            logger.warning("ADMIN_API_KEY 미설정 - 관리자 엔드포인트 비활성화")
            return jsonify({"error": "관리자 기능이 비활성화되어 있습니다"}), 503
        provided = request.headers.get("X-Admin-Key", "")
        if provided != ADMIN_API_KEY:
            return jsonify({"error": "인증이 필요합니다"}), 401
        return fn(*args, **kwargs)
    return wrapper


# 챗봇/DB/VectorStore 싱글턴 (지연 초기화)
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
    """챗봇이 이미 로딩한 VectorStore 재사용 (임베딩 모델 중복 로딩 방지)"""
    global _vector_store
    if _vector_store is None:
        bot = get_chatbot()
        _vector_store = bot.retriever.vs
    return _vector_store


@app.route("/")
def index():
    """메인 챗봇 페이지"""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
@limiter.limit(RATE_LIMIT_CHAT)
def chat():
    """챗봇 대화 API"""
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "메시지를 입력해주세요"}), 400

    user_message = data["message"].strip()
    if not user_message:
        return jsonify({"error": "빈 메시지입니다"}), 400

    if len(user_message) > 500:
        return jsonify({"error": "메시지가 너무 깁니다 (최대 500자)"}), 400

    session_id = session.get("session_id", str(uuid.uuid4()))

    try:
        bot = get_chatbot()
        result = bot.chat(session_id, user_message)
        return jsonify({
            "answer": result["answer"],
            "sources": result["sources"],
            "is_clarification": result["is_clarification"],
        })
    except Exception as e:
        logger.error(f"챗봇 오류: {e}", exc_info=True)
        return jsonify({
            "answer": "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            "sources": [],
            "is_clarification": False,
        }), 500


@app.route("/api/clear", methods=["POST"])
def clear_chat():
    """대화 초기화 API"""
    session_id = session.get("session_id")
    if session_id:
        try:
            bot = get_chatbot()
            bot.clear_session(session_id)
        except Exception as e:
            logger.error(f"대화 초기화 오류: {e}")

    session["session_id"] = str(uuid.uuid4())
    return jsonify({"status": "ok"})


@app.route("/api/stats", methods=["GET"])
@require_admin
@limiter.limit("30 per minute")
def stats():
    """시스템 통계 API (관리자 전용)"""
    try:
        db = get_db()
        vs = get_vector_store()
        db_stats = db.stats()
        vs_stats = vs.collection_stats()
        return jsonify({**db_stats, **vs_stats})
    except Exception as e:
        # 상세 에러는 서버 로그에만 남기고, 클라이언트에는 일반화된 메시지 반환
        logger.error(f"/api/stats 오류: {e}", exc_info=True)
        return jsonify({"error": "시스템 오류가 발생했습니다"}), 500


# 홈페이지 연동용 iframe/위젯 엔드포인트
@app.route("/widget")
def widget():
    """홈페이지 임베딩용 위젯 (iframe)"""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return render_template("widget.html")


def run_server():
    # 서버 시작 전 챗봇 미리 초기화 (임베딩 모델 로딩)
    logger.info("챗봇 사전 초기화 중 (임베딩 모델 로딩)...")
    try:
        get_chatbot()
        logger.info("챗봇 사전 초기화 완료!")
    except Exception as e:
        logger.warning(f"챗봇 사전 초기화 실패 (첫 요청 시 재시도): {e}")

    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)


if __name__ == "__main__":
    run_server()
