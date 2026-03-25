"""
MySQL DB - 원본 크롤링 데이터 및 정제 청크 저장
"""

import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, Integer, DateTime, Boolean, Index
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.dialects.mysql import LONGTEXT

from config import MYSQL_URL

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class RawPage(Base):
    __tablename__ = "raw_pages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(500), unique=True, nullable=False)
    title = Column(String(300))
    content = Column(LONGTEXT)
    category = Column(String(100))
    sub_category = Column(String(300))
    content_hash = Column(String(32))           # 변경 감지용 MD5 해시
    crawled_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_pages_category", "category"),
    )


class ProcessedChunk(Base):
    __tablename__ = "processed_chunks"

    chunk_id = Column(String(32), primary_key=True)
    url = Column(String(500), nullable=False)
    title = Column(String(300))
    content = Column(Text)
    category = Column(String(100))
    sub_category = Column(String(300))
    chunk_index = Column(Integer)
    total_chunks = Column(Integer)
    service_type = Column(String(50))
    target_audience = Column(String(300))
    keywords = Column(String(300))
    has_deadline = Column(Boolean, default=False)
    has_contact_info = Column(Boolean, default=False)
    summary = Column(String(200))
    embedded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_chunks_category", "category"),
        Index("ix_chunks_service_type", "service_type"),
        Index("ix_chunks_embedded", "embedded"),
        Index("ix_chunks_url", "url"),
    )


class Database:
    def __init__(self):
        self.engine = create_engine(
            MYSQL_URL,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        logger.info(f"MySQL DB 연결: {MYSQL_URL.split('@')[-1]}")

    def save_raw_page(self, page_data) -> bool:
        """원본 페이지 저장 (중복 URL 스킵)"""
        import hashlib
        content_hash = hashlib.md5(page_data.content.encode()).hexdigest()

        with self.Session() as session:
            exists = session.query(RawPage).filter_by(url=page_data.url).first()
            if exists:
                return False
            row = RawPage(
                url=page_data.url,
                title=page_data.title,
                content=page_data.content,
                category=page_data.category,
                sub_category=page_data.sub_category,
                content_hash=content_hash,
            )
            session.add(row)
            session.commit()
            return True

    def upsert_raw_page(self, page_data) -> str:
        """
        증분 크롤링용 저장
        - 신규 URL: 저장 → 'new' 반환
        - 내용 변경: 업데이트 → 'updated' 반환
        - 변경 없음: 스킵 → 'unchanged' 반환
        """
        import hashlib
        content_hash = hashlib.md5(page_data.content.encode()).hexdigest()

        with self.Session() as session:
            exists = session.query(RawPage).filter_by(url=page_data.url).first()

            if not exists:
                row = RawPage(
                    url=page_data.url,
                    title=page_data.title,
                    content=page_data.content,
                    category=page_data.category,
                    sub_category=page_data.sub_category,
                    content_hash=content_hash,
                )
                session.add(row)
                session.commit()
                return "new"

            if exists.content_hash == content_hash:
                return "unchanged"

            # 내용이 변경된 경우 업데이트
            exists.title = page_data.title
            exists.content = page_data.content
            exists.sub_category = page_data.sub_category
            exists.content_hash = content_hash
            exists.updated_at = datetime.utcnow()
            session.commit()

            # 해당 URL의 기존 청크 삭제 (재처리 필요)
            session.query(ProcessedChunk).filter_by(url=page_data.url).delete()
            session.commit()
            return "updated"

    def get_all_urls(self) -> set:
        """DB에 저장된 모든 URL 반환"""
        with self.Session() as session:
            rows = session.query(RawPage.url).all()
            return {r.url for r in rows}

    def delete_page(self, url: str):
        """페이지 및 관련 청크 삭제 (사라진 페이지 처리)"""
        with self.Session() as session:
            session.query(ProcessedChunk).filter_by(url=url).delete()
            session.query(RawPage).filter_by(url=url).delete()
            session.commit()

    def get_pages_by_urls(self, urls: list) -> list:
        """특정 URL 목록의 페이지 조회"""
        with self.Session() as session:
            rows = session.query(RawPage).filter(RawPage.url.in_(urls)).all()
            session.expunge_all()
            return rows

    def save_chunks_bulk(self, tagged_chunks: list):
        """청크 일괄 저장"""
        import json
        with self.Session() as session:
            new_count = 0
            for chunk, metadata in tagged_chunks:
                exists = session.query(ProcessedChunk).filter_by(chunk_id=chunk.chunk_id).first()
                if exists:
                    continue
                row = ProcessedChunk(
                    chunk_id=chunk.chunk_id,
                    url=chunk.url,
                    title=chunk.title,
                    content=chunk.content,
                    category=chunk.category,
                    sub_category=chunk.sub_category,
                    chunk_index=chunk.chunk_index,
                    total_chunks=chunk.total_chunks,
                    service_type=metadata.get("service_type", "기타"),
                    target_audience=json.dumps(metadata.get("target_audience", []), ensure_ascii=False),
                    keywords=json.dumps(metadata.get("keywords", []), ensure_ascii=False),
                    has_deadline=metadata.get("has_deadline", False),
                    has_contact_info=metadata.get("has_contact_info", False),
                    summary=metadata.get("summary", ""),
                )
                session.add(row)
                new_count += 1
            session.commit()
            logger.info(f"DB 저장 완료: {new_count}개 청크")

    def get_unembedded_chunks(self) -> list:
        """벡터 임베딩 안 된 청크 조회"""
        with self.Session() as session:
            rows = session.query(ProcessedChunk).filter_by(embedded=False).all()
            session.expunge_all()
            return rows

    def mark_embedded(self, chunk_ids: list[str]):
        """임베딩 완료 표시"""
        with self.Session() as session:
            session.query(ProcessedChunk)\
                .filter(ProcessedChunk.chunk_id.in_(chunk_ids))\
                .update({"embedded": True}, synchronize_session=False)
            session.commit()

    def stats(self) -> dict:
        with self.Session() as session:
            raw = session.query(RawPage).count()
            chunks = session.query(ProcessedChunk).count()
            embedded = session.query(ProcessedChunk).filter_by(embedded=True).count()
            return {"raw_pages": raw, "chunks": chunks, "embedded": embedded}
