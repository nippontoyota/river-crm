import logging
import os
from time import perf_counter

from django.db import connection


logger = logging.getLogger("crm.performance")


class PerformanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.slow_seconds = float(os.environ.get("SLOW_REQUEST_SECONDS", "0.5"))

    def __call__(self, request):
        query_count = 0
        database_seconds = 0.0

        def measure(execute, sql, params, many, context):
            nonlocal query_count, database_seconds
            started = perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                query_count += 1
                database_seconds += perf_counter() - started

        started = perf_counter()
        with connection.execute_wrapper(measure):
            response = self.get_response(request)
        elapsed = perf_counter() - started
        response["Server-Timing"] = f'app;dur={elapsed * 1000:.1f}, db;dur={database_seconds * 1000:.1f};desc="{query_count} queries"'
        if elapsed >= self.slow_seconds:
            logger.warning(
                "slow_request method=%s path=%s status=%s duration_ms=%.1f db_ms=%.1f queries=%s",
                request.method, request.path, response.status_code, elapsed * 1000, database_seconds * 1000, query_count,
            )
        return response
