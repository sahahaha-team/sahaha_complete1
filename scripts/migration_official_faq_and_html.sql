-- 구청 공식 예상질문 정답셋과 구조화 HTML 원본 저장

alter table public.raw_pages
  add column if not exists raw_html text;

create table if not exists public.official_faq (
  id integer primary key,
  question text not null unique,
  approved_answer text not null,
  source_url text not null,
  category text not null default '기타',
  keywords jsonb not null default '[]'::jsonb,
  is_time_sensitive boolean not null default false,
  verified_at date,
  updated_at timestamp with time zone not null default now()
);

create index if not exists ix_official_faq_category
  on public.official_faq(category);

alter table public.official_faq enable row level security;

drop policy if exists "official_faq_anon_select" on public.official_faq;
create policy "official_faq_anon_select" on public.official_faq
  for select to anon, authenticated using (true);

revoke insert, update, delete on public.official_faq from anon, authenticated;
grant select on public.official_faq to anon, authenticated;
