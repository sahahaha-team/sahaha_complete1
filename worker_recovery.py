"""Recover overdue maintenance after sleep/restart, using durable success times.

The OS lock is shared by cron and recovery calls, including another Worker
process. A failed/partial operation never advances last_success_at.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


@contextmanager
def process_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+b')
    acquired = False
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (OSError, BlockingIOError):
            pass
        yield acquired
    finally:
        if acquired:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def timestamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class RefreshTask:
    name: str
    callback: Callable
    interval: timedelta = timedelta(days=1)


class IncompleteRefresh(RuntimeError):
    def __init__(self, result):
        super().__init__('Some official sources could not be verified')
        self.result = result


class RefreshCoordinator:
    def __init__(self, tasks: list[RefreshTask], state_path: Path, *, now=None):
        self.tasks = {task.name: task for task in tasks}
        self.state_path = state_path
        self.lock_path = state_path.with_suffix('.lock')
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _read(self):
        try:
            state = json.loads(self.state_path.read_text(encoding='utf-8'))
            if not isinstance(state, dict) or not isinstance(state.get('jobs'), dict):
                raise ValueError('invalid state')
            return state
        except (OSError, ValueError, TypeError):
            return {'schema_version': 1, 'jobs': {}}

    def due(self, task: RefreshTask, row: dict, now: datetime):
        retry = timestamp(row.get('next_retry_at'))
        if retry and now < retry <= now + timedelta(hours=6):
            return False
        if row.get('status') in ('failed', 'partial', 'running'):
            return True
        last = timestamp(row.get('last_success_at'))
        return not last or last > now + timedelta(minutes=5) or now - last >= task.interval

    def run(self, name: str, *, force=False):
        task = self.tasks[name]
        with process_lock(self.lock_path) as acquired:
            if not acquired:
                logger.info('유지보수 실행 중: %s는 다음 복구 검사로 이월', name)
                return 'busy'
            state = self._read()
            row = state['jobs'].setdefault(name, {})
            now = self.now()
            if not force and not self.due(task, row, now):
                return 'current'
            row.update(status='running', last_attempt_at=now.isoformat())
            self._write(state)
            logger.info('유지보수 실행: %s', name)
            try:
                result = task.callback()
                if isinstance(result, dict) and any(result.get(key, 0) for key in ('errors', 'failed_pages', 'failed')):
                    raise IncompleteRefresh(result)
            except Exception as exc:
                failures = int(row.get('consecutive_failures') or 0) + 1
                delay = min(360, 30 * 2 ** min(failures - 1, 4))
                row.update(status='partial' if isinstance(exc, IncompleteRefresh) else 'failed',
                           consecutive_failures=failures, last_error_type=type(exc).__name__,
                           next_retry_at=(self.now() + timedelta(minutes=delay)).isoformat())
                if isinstance(exc, IncompleteRefresh):
                    row['last_result'] = exc.result
                self._write(state)
                logger.warning('유지보수 %s: %s, %s분 뒤 재시도', name, row['status'], delay)
                return row['status']
            row.update(status='succeeded', last_success_at=self.now().isoformat(),
                       consecutive_failures=0, next_retry_at=None, last_error_type=None)
            if isinstance(result, dict):
                row['last_result'] = result
            self._write(state)
            logger.info('유지보수 완료: %s', name)
            return 'succeeded'

    def check_overdue(self):
        # One job per tick bounds catch-up load and keeps priority updates
        # ahead of a broad crawl. Every run rechecks state under the OS lock.
        state = self._read()
        now = self.now()
        for task in self.tasks.values():
            if self.due(task, state['jobs'].get(task.name, {}), now):
                return self.run(task.name)
        return 'current'

    def _write(self, state):
        from scripts.build_contact_directory import atomic_save
        atomic_save(state, self.state_path)
