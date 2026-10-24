from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import StatusChangeLog
from common.permissions.admin_auth import AdminSessionAuthentication, AdminSessionAuthentication, IsAuthenticatedAdmin
from matters.models import Matter
from .models import MatterTask


class AdminMatterTaskCreateView(APIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def post(self, request, matter_id):
        title = request.data.get("title")
        due_date_value = request.data.get(
            "dueDate", request.data.get("due_date")
        )

        if not isinstance(title, str) or not title.strip():
            return Response(
                {"error": "title_required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        due_date = None
        if due_date_value not in (None, ""):
            try:
                due_date = date.fromisoformat(due_date_value)
            except (TypeError, ValueError):
                return Response(
                    {"error": "invalid_due_date", "expected": "YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        matter = get_object_or_404(Matter, pk=matter_id)

        task = MatterTask.objects.create(
            matter=matter,
            title=title.strip(),
            due_date=due_date,
        )

        return Response(
            {
                "id": task.pk,
                "matterId": matter.pk,
                "title": task.title,
                "status": task.status,
                "dueDate": task.due_date,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminTaskUpdateView(APIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def patch(self, request, task_id):
        task = get_object_or_404(
            MatterTask.objects.select_related("matter"),
            pk=task_id,
        )

        allowed_fields = {"status", "dueDate", "due_date"}
        if not request.data or not set(request.data.keys()).issubset(
            allowed_fields
        ):
            return Response(
                {
                    "error": "invalid_fields",
                    "allowedFields": ["status", "dueDate"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = task.status
        new_status = request.data.get("status", old_status)

        valid_statuses = {
            value for value, _label in MatterTask._meta
            .get_field("status").choices
        }

        if new_status not in valid_statuses:
            return Response(
                {
                    "error": "invalid_task_status",
                    "allowedStatuses": sorted(valid_statuses),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        due_date_supplied = (
            "dueDate" in request.data or "due_date" in request.data
        )
        due_date_value = request.data.get(
            "dueDate", request.data.get("due_date")
        )

        if due_date_supplied:
            if due_date_value in (None, ""):
                task.due_date = None
            else:
                try:
                    task.due_date = date.fromisoformat(due_date_value)
                except (TypeError, ValueError):
                    return Response(
                        {
                            "error": "invalid_due_date",
                            "expected": "YYYY-MM-DD",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        task.status = new_status

        update_fields = []
        if "status" in request.data:
            update_fields.append("status")
        if due_date_supplied:
            update_fields.append("due_date")

        if update_fields:
            task.save(update_fields=update_fields)

        if old_status != new_status:
            StatusChangeLog.objects.create(
                entity_type="task",
                entity_id=str(task.pk),
                from_status=old_status,
                to_status=new_status,
                admin_user=request.user,
            )

        return Response(
            {
                "id": task.pk,
                "matterId": task.matter_id,
                "title": task.title,
                "status": task.status,
                "dueDate": task.due_date,
            }
        )
