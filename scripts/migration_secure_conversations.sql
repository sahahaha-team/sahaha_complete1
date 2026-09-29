-- 대화 이력 anon 접근 차단 마이그레이션
-- Supabase SQL Editor에서 한 번 실행한다. 반복 실행해도 안전하다.

alter table public.conversation_logs enable row level security;

drop policy if exists "conv_anon_insert" on public.conversation_logs;
drop policy if exists "conv_anon_select" on public.conversation_logs;
drop policy if exists "conv_anon_delete" on public.conversation_logs;

revoke all on table public.conversation_logs from anon;

-- 백엔드는 SUPABASE_SERVICE_KEY(service_role)로만 대화 이력을 처리한다.
