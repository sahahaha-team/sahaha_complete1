-- ============================================
-- 사하구청 AI 상담사 - Supabase 초기 설정
-- Supabase Dashboard > SQL Editor 에서 실행
-- ============================================

-- 1. pgvector 확장 활성화
create extension if not exists vector;

-- 2. 문서 벡터 테이블 생성
create table if not exists documents (
  id text primary key,
  content text not null,
  embedding vector(384),
  metadata jsonb default '{}',
  created_at timestamp with time zone default now()
);

-- 3. 벡터 인덱스 (코사인 유사도) - hnsw는 소규모 데이터에서도 정확
drop index if exists ix_documents_embedding;
create index ix_documents_embedding
  on documents using hnsw (embedding vector_cosine_ops);

-- 4. 메타데이터 GIN 인덱스 (JSON 필터링 가속)
drop index if exists ix_documents_metadata;
create index ix_documents_metadata
  on documents using gin (metadata);

-- 5. 유사도 검색 함수 (하이브리드 검색 지원)
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
