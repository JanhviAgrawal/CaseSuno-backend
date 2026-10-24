
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions.admin_auth import (
    AdminSessionAuthentication,
    IsAuthenticatedAdmin,
)
from .models import StatusChangeLog


class AdminAuditLogListView(APIView):
    """
    Read-only audit history for authenticated CASE SUNO administrators.

    GET /api/audit/admin/logs/
    Optional query parameters:
      - entity_type
      - entity_id
      - limit (maximum 100)
    """

    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def get(self, request):
        logs = StatusChangeLog.objects.select_related(
            "admin_user"
        ).order_by("-changed_at", "-pk")

        entity_type = request.query_params.get("entity_type")
        entity_id = request.query_params.get("entity_id")

        if entity_type:
            logs = logs.filter(entity_type=entity_type)

        if entity_id:
            logs = logs.filter(entity_id=entity_id)

        limit_value = request.query_params.get("limit", "50")

        try:
            limit = int(limit_value)
        except (TypeError, ValueError):
            return Response(
                {
                    "error": "invalid_limit",
                    "message": "Limit must be an integer between 1 and 100.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not 1 <= limit <= 100:
            return Response(
                {
                    "error": "invalid_limit",
                    "message": "Limit must be between 1 and 100.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        logs = logs[:limit]

        results = []

        for log in logs:
            results.append(
                {
                    "id": log.pk,
                    "entityType": log.entity_type,
                    "entityId": log.entity_id,
                    "fromStatus": log.from_status,
                    "toStatus": log.to_status,
                    "adminUserId": log.admin_user_id,
                    "adminUserName": (
                        log.admin_user.name
                        if log.admin_user
                        else None
                    ),
                    "changedAt": log.changed_at.isoformat(),
                }
            )

        return Response(
            {
                "count": len(results),
                "results": results,
            },
            status=status.HTTP_200_OK,
        )
