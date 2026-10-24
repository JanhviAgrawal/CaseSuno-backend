"""
Access control for the /api/web/ endpoints used by the casesuno.in website.

The Next.js website talks to this API from its *server* (never from the browser),
so it can send a shared secret (X-Website-Key) and the real visitor IP
(X-Client-IP). Rate limits are applied per visitor IP, not per website server.
"""

import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.throttling import ScopedRateThrottle

WEBSITE_KEY_HEADER = "HTTP_X_WEBSITE_KEY"
CLIENT_IP_HEADER = "HTTP_X_CLIENT_IP"


def request_has_website_key(request) -> bool:
    expected = getattr(settings, "WEBSITE_API_KEY", "")
    if not expected:
        return False
    supplied = request.META.get(WEBSITE_KEY_HEADER, "")
    return bool(supplied) and hmac.compare_digest(supplied, expected)


class FromWebsite(BasePermission):
    """Require the shared website key when WEBSITE_API_KEY is configured."""

    message = "Forbidden"

    def has_permission(self, request, view):
        if not getattr(settings, "WEBSITE_API_KEY", ""):
            return True  # local development without a key
        return request_has_website_key(request)


class WebsiteRateThrottle(ScopedRateThrottle):
    """
    Scoped throttle that
      * understands rates such as "6/10m" (6 requests per 10 minutes), and
      * identifies visitors by X-Client-IP when the request comes from the website server.
    """

    def get_ident(self, request):
        if request_has_website_key(request) or not getattr(settings, "WEBSITE_API_KEY", ""):
            client_ip = request.META.get(CLIENT_IP_HEADER, "").strip()
            if client_ip:
                return client_ip[:64]
        return super().get_ident(request)

    def get_cache_key(self, request, view):
        # Always key public website limits by visitor (never by admin user id)
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }

    def parse_rate(self, rate):
        if rate is None:
            return (None, None)
        num, period = rate.split("/")
        multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        period = period.strip()
        unit = period[-1] if period[-1] in multiplier else period[0]
        digits = period[:-1] if period[-1] in multiplier else ""
        count = int(digits) if digits.isdigit() else 1
        if period[0] in multiplier and not digits:
            unit = period[0]
        return int(num), count * multiplier[unit]
