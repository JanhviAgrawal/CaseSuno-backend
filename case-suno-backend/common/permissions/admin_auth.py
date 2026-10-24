import hashlib

from django.utils import timezone

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from accounts.models import AdminUser, AdminSession

class AdminSessionAuthentication(BaseAuthentication):
    cookie_name = "case_suno_admin_session"

    header_keyword = "AdminSession"

    def get_raw_token(self, request):
        """
        The token may arrive either as the httpOnly cookie (browser -> API) or as
        "Authorization: AdminSession <token>" (website server -> API).
        """
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if header.startswith(self.header_keyword + " "):
            return header[len(self.header_keyword) + 1:].strip()
        return request.COOKIES.get(self.cookie_name)

    def authenticate(self, request):
        raw_token = self.get_raw_token(request)

        if not raw_token:
            return None

        token_hash = hashlib.sha256(
            raw_token.encode("utf-8")
        ).hexdigest()

        session = (
            AdminSession.objects.select_related("admin_user")
            .filter(
                token_hash=token_hash,
                expires_at__gt=timezone.now(),
                revoked_at__isnull=True,
                admin_user__is_active=True,
            )
            .first()
        )

        if session is None:
            raise AuthenticationFailed("Invalid or expired admin session.")

        return (session.admin_user, session)

    def authenticate_header(self, request):
        return "AdminSession"


class IsAuthenticatedAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            isinstance(request.user, AdminUser)
            and request.user.is_active
        )
