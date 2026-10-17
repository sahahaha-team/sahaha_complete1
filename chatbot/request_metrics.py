"""Request-scoped timings without question text, source bodies or credentials."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import logging
import time
import uuid

logger = logging.getLogger(__name__)
_current = ContextVar('consultation_metrics', default=None)


@dataclass
class RequestMetrics:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started: float = field(default_factory=time.perf_counter)
    timings: dict = field(default_factory=dict)
    model_calls: list = field(default_factory=list)
    decisions: list = field(default_factory=list)

    def server_timing(self):
        return ', '.join(f'{key};dur={value * 1000:.1f}' for key, value in self.timings.items())

    def summary(self):
        return {'request_id': self.request_id, 'seconds': self.timings,
                'model_calls': self.model_calls, 'decisions': self.decisions}


@contextmanager
def request_metrics():
    metrics = RequestMetrics()
    token = _current.set(metrics)
    try:
        yield metrics
    finally:
        metrics.timings['app'] = time.perf_counter() - metrics.started
        _current.reset(token)


@contextmanager
def measure(stage):
    metrics = _current.get()
    started = time.perf_counter()
    try:
        yield
    finally:
        if metrics is not None:
            metrics.timings[stage] = metrics.timings.get(stage, 0) + time.perf_counter() - started


def decision(value):
    metrics = _current.get()
    if metrics is not None:
        metrics.decisions.append(value)


def add_duration(stage, seconds):
    metrics = _current.get()
    if metrics is not None:
        metrics.timings[stage] = metrics.timings.get(stage, 0) + seconds


def record_model(seconds, metadata=None, *, outcome, error=None):
    metrics = _current.get()
    if metrics is None:
        return
    metadata = metadata or {}
    row = {'seconds': seconds, 'outcome': outcome,
           'submission_attempted': not error or type(error).__name__ != 'ModelBusy'}
    for name in ('load_duration', 'prompt_eval_duration', 'eval_duration', 'total_duration'):
        value = metadata.get(name)
        row[name + '_seconds'] = value / 1e9 if isinstance(value, (int, float)) else None
    for name in ('prompt_eval_count', 'eval_count', 'done_reason'):
        row[name] = metadata.get(name)
    if error:
        row['error_type'] = type(error).__name__
    metrics.model_calls.append(row)


def model_failure_reason():
    metrics = _current.get()
    if not metrics:
        return None
    failures = [row for row in metrics.model_calls if row['outcome'] == 'error']
    if not failures:
        return None
    error = failures[-1].get('error_type')
    return ('processing_timeout' if error == 'TimeoutError' else
            'model_busy' if error == 'ModelBusy' else 'model_unavailable')

