import hashlib
import json
import logging
from functools import wraps

from django.conf import settings
from django.core.cache import caches
from rest_framework.response import Response


logger = logging.getLogger(__name__)
_MISSING = object()
cache = caches["analytics"]


def analytics_cache_key(request, endpoint):
    user = request.user
    identity = {
        "endpoint": endpoint,
        "user_id": user.pk,
        "role": getattr(user, "role", ""),
        "location": getattr(user, "location", "").strip(),
        "query": [
            (key, sorted(request.query_params.getlist(key)))
            for key in sorted(request.query_params)
        ],
    }
    digest = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
    return f"analytics:v1:{digest}"


def cache_analytics(endpoint):
    def decorator(view):
        @wraps(view)
        def wrapped(self, request, *args, **kwargs):
            ttl = settings.CACHE_TTL_SECONDS
            if ttl <= 0:
                response = view(self, request, *args, **kwargs)
                response["X-Cache"] = "BYPASS"
                return response

            key = analytics_cache_key(request, endpoint)
            try:
                payload = cache.get(key, _MISSING)
            except Exception as error:
                logger.warning("Analytics cache read failed: %s", type(error).__name__)
                response = view(self, request, *args, **kwargs)
                response["X-Cache"] = "ERROR"
                return response

            if payload is not _MISSING:
                response = Response(payload)
                response["X-Cache"] = "HIT"
                return response

            response = view(self, request, *args, **kwargs)
            if response.status_code != 200:
                response["X-Cache"] = "BYPASS"
                return response
            try:
                cache.set(key, response.data, timeout=ttl)
                response["X-Cache"] = "MISS"
            except Exception as error:
                logger.warning("Analytics cache write failed: %s", type(error).__name__)
                response["X-Cache"] = "ERROR"
            return response

        return wrapped

    return decorator
