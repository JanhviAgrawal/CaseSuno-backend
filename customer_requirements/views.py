from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RequirementCreateSerializer 
from .models import Requirement
from .serializers import RequirementPublicSerializer
from rest_framework.throttling import AnonRateThrottle

from accounts.models import AdminUser
from common.permissions.admin_auth import (
    AdminSessionAuthentication,
    IsAuthenticatedAdmin,
)
from .serializers import AdminRequirementDetailSerializer
from .serializers import AdminRequirementListSerializer
from rest_framework import generics
from rest_framework.authentication import SessionAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from .serializers import RequirementStatusUpdateSerializer
from common.services.state_machine import (
    is_valid_requirement_transition,
)
from audit.models import StatusChangeLog

class RequirementCreateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = RequirementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT nextval('customer_requirements_reference_seq')"
                )
                sequence_number = cursor.fetchone()[0]

            year = timezone.now().year
            reference_id = f"CS-{year}-{sequence_number:05d}"

            requirement = serializer.save(
                reference_id=reference_id
            )

        return Response(
            {
                "referenceId": requirement.reference_id,
                "status": requirement.status,
            },
            status=status.HTTP_201_CREATED,
        )
        
class RequirementLookupView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def get(self, request, ref):
        try:
            requirement = Requirement.objects.get(
                reference_id=ref
            )
        except Requirement.DoesNotExist:
            return Response(
                {"error": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = RequirementPublicSerializer(
            requirement
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
        
        
        
class AdminRequirementPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class AdminRequirementListView(generics.ListAPIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]
    
    serializer_class = AdminRequirementListSerializer
    pagination_class = AdminRequirementPagination

    def get_queryset(self):
        queryset = Requirement.objects.all().order_by("-created_at")

        status_filter = self.request.query_params.get("status")
        urgency_filter = self.request.query_params.get("urgency")

        valid_statuses = {
            value
            for value, label in Requirement._meta
            .get_field("status").choices
        }

        valid_urgencies = {
            value
            for value, label in Requirement._meta
            .get_field("urgency").choices
        }

        if status_filter:
            if status_filter not in valid_statuses:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({
                    "status": "Invalid status filter."
                })

            queryset = queryset.filter(status=status_filter)

        if urgency_filter:
            if urgency_filter not in valid_urgencies:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({
                    "urgency": "Invalid urgency filter."
                })

            queryset = queryset.filter(urgency=urgency_filter)

        return queryset

class AdminRequirementDetailView(generics.RetrieveAPIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]
    serializer_class = AdminRequirementDetailSerializer
    queryset = Requirement.objects.all()
    

class AdminRequirementStatusUpdateView(APIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def patch(self, request, pk):
        serializer = RequirementStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_status = serializer.validated_data["status"]

        with transaction.atomic():
            requirement = (
                Requirement.objects.select_for_update()
                .filter(pk=pk)
                .first()
            )

            if requirement is None:
                return Response(
                    {"error": "not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            current_status = requirement.status

            if not is_valid_requirement_transition(
                current_status,
                target_status,
            ):
                return Response(
                    {
                        "error": "invalid_transition",
                        "from": current_status,
                        "to": target_status,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            requirement.status = target_status
            update_fields = ["status"]

            notes = request.data.get("internalNotes", request.data.get("internal_notes"))
            if notes is not None:
                requirement.internal_notes = str(notes).strip()
                update_fields.append("internal_notes")

            if (
                target_status == "reviewed"
                and isinstance(request.user, AdminUser)
            ):
                requirement.reviewed_by = request.user
                update_fields.append("reviewed_by")

            requirement.save(update_fields=update_fields)

            StatusChangeLog.objects.create(
                entity_type="requirement",
                entity_id=requirement.id,
                from_status=current_status,
                to_status=target_status,
                admin_user=request.user,
            )

        return Response(
            {
                "id": requirement.id,
                "referenceId": requirement.reference_id,
                "status": requirement.status,
                "internalNotes": requirement.internal_notes,
            },
            status=status.HTTP_200_OK,
        )


class AdminRequirementNotesUpdateView(APIView):
    """
    Update internal notes on a requirement without altering its status.
    PATCH /api/requirements/admin/<pk>/notes/
    """
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def patch(self, request, pk):
        notes = request.data.get("internalNotes", request.data.get("internal_notes"))
        if notes is None:
            return Response(
                {"error": "internalNotes_required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requirement = get_object_or_404(Requirement, pk=pk)
        requirement.internal_notes = str(notes).strip()
        requirement.save(update_fields=["internal_notes"])

        return Response(
            {
                "id": requirement.id,
                "referenceId": requirement.reference_id,
                "internalNotes": requirement.internal_notes,
                "message": "internal_notes_updated",
            },
            status=status.HTTP_200_OK,
        )




# $body = @{
#     email = "sachinwork1518@gmail.com"
#     otp   = "009797"
# } | ConvertTo-Json

# Invoke-RestMethod `
#     -Uri "http://127.0.0.1:8000/api/accounts/admin/login/" `
#     -Method POST `
#     -ContentType "application/json" `
#     -Body $body `
#     -WebSession $session

