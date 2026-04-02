"""
사하구청 AI 상담사 - Flask 웹 애플리케이션
"""

import uuid
import logging
from flask import Flask, render_template, request, jsonify, session

from config import SECRET_KEY, FLASK_HOST, FLASK_PORT, FLASK_DEBUG

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 챗봇 인스턴스 (지연 초기화)
_chatbot = None


def get_chatbot():
    global _chatbot
    if _chatbot is None:
        from chatbot.conversation import ChatBot
        _chatbot = ChatBot()
    return _chatbot


@app.route("/")
def index():
    """메인 챗봇 페이지"""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
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
def stats():
    """시스템 통계 API"""
    try:
        from database_db.database import Database
        from database_db.vector_store import VectorStore
        db = Database()
        vs = VectorStore()
        db_stats = db.stats()
        vs_stats = vs.collection_stats()
        return jsonify({**db_stats, **vs_stats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
