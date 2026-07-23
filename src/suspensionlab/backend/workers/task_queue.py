import os
from redis import Redis
from rq import Queue

_redis_conn = None
_job_queue = None

def _get_redis_conn():
    global _redis_conn
    if _redis_conn is None:
        redis_url = os.getenv("REDIS_URL", "")
        if not redis_url:
            raise RuntimeError("REDIS_URL is not set — Redis-backed features unavailable.")
        _redis_conn = Redis.from_url(redis_url, socket_timeout=5.0, socket_connect_timeout=5.0)
    return _redis_conn

_priority_job_queue = None

def _get_job_queue():
    global _job_queue
    if _job_queue is None:
        _job_queue = Queue("default", connection=_get_redis_conn())
    return _job_queue

def _get_priority_job_queue():
    global _priority_job_queue
    if _priority_job_queue is None:
        _priority_job_queue = Queue("priority_queue", connection=_get_redis_conn())
    return _priority_job_queue

# Proxy objects so existing code that does `from queue import job_queue` still works
class _LazyQueue:
    def __getattr__(self, name):
        return getattr(_get_job_queue(), name)
    def enqueue(self, *args, **kwargs):
        return _get_job_queue().enqueue(*args, **kwargs)

class _LazyPriorityQueue:
    def __getattr__(self, name):
        return getattr(_get_priority_job_queue(), name)
    def enqueue(self, *args, **kwargs):
        return _get_priority_job_queue().enqueue(*args, **kwargs)

class _LazyRedis:
    @property
    def connection(self):
        return _get_redis_conn()
    def __getattr__(self, name):
        return getattr(_get_redis_conn(), name)

job_queue = _LazyQueue()
priority_job_queue = _LazyPriorityQueue()
redis_conn = _LazyRedis()
