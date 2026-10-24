
from django.core.paginator import Paginator, EmptyPage
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions.admin_auth import (
    AdminSessionAuthentication,
    IsAuthenticatedAdmin,
)
from common.services.state_machine import is_valid_matter_transition

from audit.models import StatusChangeLog
from documents.models import MatterDocument
from tasks.models import MatterTask
from professionals.models import Professional
from matters.tasks import send_status_notification_task

from .models import Matter


class AdminMatterListView(APIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def get(self, request):
        queryset = (
            Matter.objects
            .select_related("proposal", "proposal__requirement")
            .order_by("-opened_at", "-id")
        )

        # Optional status filter
        requested_status = request.query_params.get("status")

        if requested_status:
            valid_statuses = {
                value for value, _label in Matter.Status.choices
            }

            if requested_status not in valid_statuses:
                return Response(
                    {
                        "error": "invalid_status",
                        "validStatuses": sorted(valid_statuses),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            queryset = queryset.filter(status=requested_status)

        # Pagination parameters
        try:
            page_number = int(request.query_params.get("page", "1"))
            page_size = int(request.query_params.get("page_size", "20"))
        except (TypeError, ValueError):
            return Response(
                {"error": "invalid_pagination_parameters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if page_number < 1 or page_size < 1 or page_size > 100:
            return Response(
                {
                    "error": "invalid_pagination_parameters",
                    "message": (
                        "page must be at least 1 and page_size "
                        "must be between 1 and 100."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        paginator = Paginator(queryset, page_size)

        try:
            page_obj = paginator.page(page_number)
        except EmptyPage:
            return Response(
                {"error": "page_out_of_range"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = [
            {
                "id": matter.pk,
                "proposalId": str(matter.proposal.public_id),
                "referenceId": matter.proposal.requirement.reference_id,
                "status": matter.status,
                "openedAt": matter.opened_at,
                "closedAt": matter.closed_at,
            }
            for matter in page_obj.object_list
        ]

        return Response(
            {
                "count": paginator.count,
                "page": page_number,
                "pageSize": page_size,
                "totalPages": paginator.num_pages,
                "nextPage": (
                    page_obj.next_page_number()
                    if page_obj.has_next()
                    else None
                ),
                "previousPage": (
                    page_obj.previous_page_number()
                    if page_obj.has_previous()
                    else None
                ),
                "results": results,
            },
            status=status.HTTP_200_OK,
        )


class AdminMatterDetailView(APIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def get(self, request, pk):
        try:
            matter = (
                Matter.objects
                .select_related("proposal", "proposal__requirement")
                .prefetch_related("professionals")
                .get(pk=pk)
            )
        except Matter.DoesNotExist:
            return Response(
                {"error": "matter_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        documents = (
            MatterDocument.objects
            .filter(matter_id=matter.pk)
            .order_by("-uploaded_at")
        )

        tasks = (
            MatterTask.objects
            .filter(matter_id=matter.pk)
            .order_by("due_date", "pk")
        )

        return Response(
            {
                "id": matter.pk,
                "proposalId": str(matter.proposal.public_id),
                "referenceId": matter.proposal.requirement.reference_id,
                "serviceName": matter.proposal.service_name,
                "status": matter.status,
                "coordinationNotes": matter.coordination_notes,
                "openedAt": matter.opened_at,
                "closedAt": matter.closed_at,
                "professionals": [
                    {
                        "id": professional.pk,
                        "name": professional.name,
                        "specialism": professional.specialism,
                        "contact": professional.contact,
                    }
                    for professional in matter.professionals.all()
                ],
                "documents": [
                    {
                        "id": document.pk,
                        "uploadedBy": str(document.uploaded_by),
                        "uploadedAt": document.uploaded_at,
                        "downloadEndpoint": (
                            f"/api/matters/admin/{matter.pk}/documents/"
                            f"{document.pk}/download/"
                        ),
                    }
                    for document in documents
                ],
                "tasks": [
                    {
                        "id": task.pk,
                        "title": task.title,
                        "status": task.status,
                        "dueDate": task.due_date,
                    }
                    for task in tasks
                ],
            },
            status=status.HTTP_200_OK,
        )


class AdminMatterStatusUpdateView(APIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def patch(self, request, pk):
        target_status = request.data.get("status")

        valid_statuses = {
            value for value, _label in Matter.Status.choices
        }

        if target_status not in valid_statuses:
            return Response(
                {
                    "error": "invalid_status",
                    "validStatuses": sorted(valid_statuses),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            try:
                matter = (
                    Matter.objects
                    .select_for_update()
                    .select_related("proposal", "proposal__requirement")
                    .get(pk=pk)
                )
            except Matter.DoesNotExist:
                return Response(
                    {"error": "matter_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            old_status = matter.status

            if not is_valid_matter_transition(
                old_status,
                target_status,
            ):
                return Response(
                    {
                        "error": "invalid_transition",
                        "from": old_status,
                        "to": target_status,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            matter.status = target_status
            update_fields = ["status"]

            notes = request.data.get("coordinationNotes", request.data.get("coordination_notes"))
            if notes is not None:
                matter.coordination_notes = str(notes).strip()
                update_fields.append("coordination_notes")

            if target_status == Matter.Status.CLOSED:
                matter.closed_at = timezone.now()
                update_fields.append("closed_at")

            matter.save(update_fields=update_fields)

            StatusChangeLog.objects.create(
                entity_type="matter",
                entity_id=str(matter.pk),
                from_status=old_status,
                to_status=target_status,
                admin_user=request.user,
            )

            requirement = matter.proposal.requirement

            subject = f"CASE SUNO matter update: {matter.pk}"
            message = (
                f"Hello {requirement.name},\n\n"
                "Your CASE SUNO matter status has been updated.\n\n"
                f"Matter ID: {matter.pk}\n"
                f"Previous status: {old_status}\n"
                f"New status: {target_status}\n\n"
                "If you have questions, please contact CASE SUNO.\n"
            )

            # Queue the notification only after the transaction commits.
            transaction.on_commit(
                lambda: send_status_notification_task.delay(
                    recipient_email=requirement.email,
                    subject=subject,
                    message=message,
                )
            )

        return Response(
            {
                "id": matter.pk,
                "status": matter.status,
                "coordinationNotes": matter.coordination_notes,
                "closedAt": matter.closed_at,
            },
            status=status.HTTP_200_OK,
        )


class AdminMatterNotesUpdateView(APIView):
    """
    Update internal coordination notes on a matter without modifying status.
    PATCH /api/matters/admin/<pk>/notes/
    """
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def patch(self, request, pk):
        notes = request.data.get("coordinationNotes", request.data.get("coordination_notes"))
        if notes is None:
            return Response(
                {"error": "coordinationNotes_required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        matter = get_object_or_404(Matter, pk=pk)
        matter.coordination_notes = str(notes).strip()
        matter.save(update_fields=["coordination_notes"])

        return Response(
            {
                "id": matter.pk,
                "coordinationNotes": matter.coordination_notes,
                "message": "coordination_notes_updated",
            },
            status=status.HTTP_200_OK,
        )



class AdminMatterProfessionalsView(APIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def patch(self, request, pk):
        professional_ids = request.data.get("professional_ids")

        if not isinstance(professional_ids, list):
            return Response(
                {"error": "professional_ids_must_be_a_list"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if any(
            isinstance(item, bool)
            or not isinstance(item, int)
            or item <= 0
            for item in professional_ids
        ):
            return Response(
                {
                    "error": (
                        "professional_ids_must_contain_positive_integers"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(professional_ids) != len(set(professional_ids)):
            return Response(
                {"error": "duplicate_professional_ids"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        matter = get_object_or_404(Matter, pk=pk)

        professionals = list(
            Professional.objects.filter(
                id__in=professional_ids,
                is_active=True,
            )
        )

        if len(professionals) != len(professional_ids):
            return Response(
                {
                    "error": "professional_not_found_or_inactive",
                    "requested_ids": professional_ids,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            matter.professionals.set(professionals)

        return Response(
            {
                "message": "professionals_assigned",
                "matter_id": matter.pk,
                "professional_ids": [
                    professional.pk
                    for professional in professionals
                ],
            },
            status=status.HTTP_200_OK,
        )


class CustomerMatterTrackingView(APIView):
    """
    Public tracking view for customers holding a valid CASE SUNO reference ID.
    GET /api/matters/tracking/<reference_id>/
    """
    permission_classes = []
    throttle_classes = []

    def get(self, request, ref):
        from customer_requirements.models import Requirement
        from customer_requirements.serializers import RequirementPublicSerializer

        requirement = get_object_or_404(
            Requirement.objects.select_related("proposal__matter"),
            reference_id=ref,
        )
        serializer = RequirementPublicSerializer(requirement)
        return Response(serializer.data, status=status.HTTP_200_OK)

