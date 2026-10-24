from django.conf import settings
from django.core.cache import cache
from django.db import connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Liveness/readiness probe used by Render (healthCheckPath: /health/)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        health_status = {
            "status": "ok",
            "database": False,
            "cache": settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1],
            "redis": "not_configured",
        }

        # PostgreSQL is required
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                health_status["database"] = True
        except Exception as exc:
            health_status["status"] = "degraded"
            health_status["database_error"] = str(exc)

        # Redis is optional — only checked when configured
        if getattr(settings, "REDIS_CACHE_URL", ""):
            try:
                cache.set("health_check_ping", "pong", timeout=10)
                health_status["redis"] = cache.get("health_check_ping") == "pong"
            except Exception as exc:
                health_status["redis"] = False
                health_status["redis_error"] = str(exc)

        http_status = (
            status.HTTP_200_OK
            if health_status["status"] == "ok"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return Response(health_status, status=http_status)


class RootView(APIView):
    """Friendly landing response for the API root URL."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        return Response(
            {
                "service": "CASE SUNO API",
                "status": "ok",
                "website": getattr(settings, "SITE_URL", ""),
                "health": "/health/",
            }
        )
