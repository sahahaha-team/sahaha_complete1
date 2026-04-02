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
  crawled_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

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
  target_audience text,
  keywords text,
  has_deadline boolean default false,
  has_contact_info boolean default false,
  summary text,
  embedded boolean default false,
  created_at timestamp with time zone default now()
);

create index if not exists ix_chunks_category on processed_chunks(category);
create index if not exists ix_chunks_service_type on processed_chunks(service_type);
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
-- 6. RLS 비활성화 (anon 키로 접근 허용)
-- ============================================
alter table documents disable row level security;
alter table raw_pages disable row level security;
alter table processed_chunks disable row level security;
alter table conversation_logs disable row level security;

-- ============================================
-- 7. 유사도 검색 함수
-- ============================================
create or replace function match_documents(
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
