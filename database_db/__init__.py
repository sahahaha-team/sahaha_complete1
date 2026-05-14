"""Supabase 클라이언트 공유 모듈"""

import logging
from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY

logger = logging.getLogger(__name__)

_public_client: Client = None
_admin_client: Client = None


def get_supabase(admin: bool = False) -> Client:
    """
    공유 Supabase 클라이언트 반환.
    - admin=False: anon 키 (RLS 적용, 일반 챗봇 요청)
    - admin=True : service role 키 (RLS 우회, 크롤링/TTL/관리 작업)
    """
    global _public_client, _admin_client

    if admin:
        if _admin_client is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
                raise ValueError(
                    "SUPABASE_URL/SUPABASE_SERVICE_KEY 미설정 - 관리자 작업 불가"
                )
            _admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            logger.info("Supabase service role 클라이언트 초기화")
        return _admin_client

    if _public_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL/SUPABASE_KEY를 .env에 설정해주세요")
        _public_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase anon 클라이언트 초기화")

    return _public_client
