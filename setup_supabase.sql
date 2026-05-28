-- ============================================
-- 사하구청 AI 상담사 - Supabase 초기 설정
-- Supabase Dashboard > SQL Editor 에서 실행
-- ============================================

-- 1. pgvector 확장 활성화
create extension if not exists vector;

-- ============================================
-- 2. 벡터 검색용 테이블 (documents)
-- ============================================
create table if not exists documents (
  id text primary key,
  content text not null,
  embedding vector(384),
  metadata jsonb default '{}',
  created_at timestamp with time zone default now()
);

drop index if exists ix_documents_embedding;
create index ix_documents_embedding
  on documents using hnsw (embedding vector_cosine_ops);

drop index if exists ix_documents_metadata;
create index ix_documents_metadata
  on documents using gin (metadata);

-- ============================================
-- 3. 크롤링 원본 데이터 (raw_pages)
-- ============================================
create table if not exists raw_pages (
  id serial primary key,
  url text unique not null,
  title text,
  content text,
  category text,
  sub_category text,
  content_hash text,
  -- HTTP 조건부 GET용 캐시 검증자 (증분 크롤링에서 If-None-Match / If-Modified-Since로 전송)
  etag text,
  last_modified text,
  crawled_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- 기존 테이블에 컬럼이 없을 경우를 위한 호환성 마이그레이션
alter table raw_pages add column if not exists etag text;
alter table raw_pages add column if not exists last_modified text;

create index if not exists ix_raw_pages_category on raw_pages(category);

-- ============================================
-- 4. 정제된 청크 데이터 (processed_chunks)
-- ============================================
create table if not exists processed_chunks (
  chunk_id text primary key,
  url text not null,
  title text,
  content text,
  category text,
  sub_category text,
  chunk_index int,
  total_chunks int,
  service_type text,
  -- 담당 부서명 (LLM이 본문에서 추출, 미명시 시 NULL)
  department text,
  target_audience text,
  keywords text,
  has_deadline boolean default false,
  has_contact_info boolean default false,
  summary text,
  embedded boolean default false,
  created_at timestamp with time zone default now()
);

-- 기존 테이블 호환성 마이그레이션
alter table processed_chunks add column if not exists department text;

create index if not exists ix_chunks_category on processed_chunks(category);
create index if not exists ix_chunks_service_type on processed_chunks(service_type);
create index if not exists ix_chunks_department on processed_chunks(department);
create index if not exists ix_chunks_embedded on processed_chunks(embedded);
create index if not exists ix_chunks_url on processed_chunks(url);

-- ============================================
-- 5. 대화 이력 (conversation_logs)
-- ============================================
create table if not exists conversation_logs (
  id serial primary key,
  session_id text not null,
  role text not null,
  content text not null,
  sources text,
  created_at timestamp with time zone default now()
);

create index if not exists ix_conv_session on conversation_logs(session_id);
create index if not exists ix_conv_session_created on conversation_logs(session_id, created_at);

-- ============================================
-- 6. RLS 정책 (anon: 읽기/대화 INSERT만, service role: 전체)
-- ============================================
-- service_role 키는 RLS를 항상 우회하므로 별도 정책 불필요.
-- 아래 정책은 anon 키 접근만 제한하기 위한 것.

alter table documents enable row level security;
alter table raw_pages enable row level security;
alter table processed_chunks enable row level security;
alter table conversation_logs enable row level security;

-- documents: 챗봇 검색을 위한 SELECT만 허용
drop policy if exists "documents_anon_select" on documents;
create policy "documents_anon_select" on documents
  for select to anon using (true);

-- raw_pages: anon 접근 차단 (관리자 작업 전용)
drop policy if exists "raw_pages_anon_no_access" on raw_pages;
-- (policy 미생성 = anon 접근 불가)

-- processed_chunks: 챗봇이 키워드/카테고리 조회용으로 SELECT 가능
drop policy if exists "processed_chunks_anon_select" on processed_chunks;
create policy "processed_chunks_anon_select" on processed_chunks
  for select to anon using (true);

-- conversation_logs:
--   - anon은 본인 세션 대화 INSERT/SELECT/DELETE만 허용
--     (session_id 기반 제한은 클라이언트가 임의 session_id를 만들 수 있으므로
--      서버에서 추가 검증을 권장. service_role 키 사용 시 정책 우회 가능)
drop policy if exists "conv_anon_insert" on conversation_logs;
create policy "conv_anon_insert" on conversation_logs
  for insert to anon with check (true);

drop policy if exists "conv_anon_select" on conversation_logs;
create policy "conv_anon_select" on conversation_logs
  for select to anon using (true);

drop policy if exists "conv_anon_delete" on conversation_logs;
create policy "conv_anon_delete" on conversation_logs
  for delete to anon using (true);
-- UPDATE는 어떤 역할에게도 허용하지 않음 (대화는 append-only)

-- ============================================
-- 7. 유사도 검색 함수
-- ============================================
-- search_path 고정으로 SECURITY DEFINER 권한 상승 공격 방지
-- (Supabase Security Advisor: Function Search Path Mutable)
create or replace function public.match_documents(
  query_embedding vector(384),
  match_count int default 5,
  filter_metadata jsonb default '{}'
)
returns table (
  id text,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
begin
  return query
  select
    d.id,
    d.content,
    d.metadata,
    1 - (d.embedding <=> query_embedding) as similarity
  from documents d
  where case
    when filter_metadata = '{}'::jsonb then true
    else d.metadata @> filter_metadata
  end
  order by d.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- 함수 실행 권한을 anon/authenticated에만 명시적으로 부여 (public 회수)
revoke all on function public.match_documents(vector, int, jsonb) from public;
grant execute on function public.match_documents(vector, int, jsonb) to anon, authenticated;
