-- ============================================
-- 첨부파일(PDF/HWP 등) 링크 노출 기능 마이그레이션
-- Supabase Dashboard > SQL Editor 에서 1회 실행
-- (idempotent: 여러 번 실행해도 안전)
-- ============================================

-- 원본 페이지: 게시물 첨부파일 목록
alter table raw_pages
  add column if not exists attachments jsonb default '[]'::jsonb;

-- 정제 청크: 페이지 첨부파일을 청크에 함께 보관 (임베딩 메타로 흐름)
alter table processed_chunks
  add column if not exists attachments jsonb default '[]'::jsonb;

-- documents.metadata 는 JSONB라 별도 컬럼/DDL 불필요
-- ("attachments" 키가 자동으로 들어가며 match_documents가 그대로 반환)

-- 적용 확인
-- select column_name from information_schema.columns
--   where table_name in ('raw_pages','processed_chunks') and column_name='attachments';
