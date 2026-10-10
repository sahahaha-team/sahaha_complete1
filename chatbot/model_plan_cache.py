"""Cache validated model selections; source facts are checked on every request."""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import threading
import time


class ModelPlanCache:
    def __init__(self, maxsize=128, ttl=300):
        self.maxsize, self.ttl = maxsize, ttl
        self._plans = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._plans.get(key)
            if not entry:
                return None
            created, plan = entry
            if time.monotonic() - created >= self.ttl:
                del self._plans[key]
                return None
            self._plans.move_to_end(key)
            return {**plan, 'units': list(plan['units'])}

    def put(self, key, plan):
        with self._lock:
            self._plans[key] = (time.monotonic(), {**plan, 'units': list(plan['units'])})
            self._plans.move_to_end(key)
            while len(self._plans) > self.maxsize:
                self._plans.popitem(last=False)


def plan_key(query, packets, keywords, llm, prompt):
    model = getattr(llm, 'model', None)
    if not isinstance(model, str):
        return None
    # Hash the full original, including conditions omitted from the bounded
    # prompt. Never store residents' query text or source bodies in the cache.
    material = {'query': query, 'model': model, 'prompt': prompt,
                'keywords': sorted(keywords), 'packets': packets}
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
        default=lambda obj: list(obj) if isinstance(obj, (set, range)) else str(obj)).encode('utf-8')).hexdigest()


model_plan_cache = ModelPlanCache()
