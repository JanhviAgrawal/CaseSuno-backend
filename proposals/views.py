
from django.db import transaction
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AdminUser
from audit.models import StatusChangeLog
from common.permissions.admin_auth import (
    AdminSessionAuthentication,
    IsAuthenticatedAdmin,
)
from common.services.state_machine import (
    is_valid_requirement_transition,
)
from customer_requirements.models import Requirement
from .models import ServiceProposal
from .serializers import ServiceProposalCreateSerializer
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny


from .serializers import ServiceProposalPublicSerializer



class AdminCreateProposalView(APIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [
        IsAuthenticatedAdmin,
    ]

    def post(self, request, pk):
        serializer = ServiceProposalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

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

            if requirement.status != "reviewed":
                return Response(
                    {
                        "error": "invalid_transition",
                        "from": requirement.status,
                        "to": "service_proposed",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if ServiceProposal.objects.filter(
                requirement=requirement
            ).exists():
                return Response(
                    {"error": "proposal_already_exists"},
                    status=status.HTTP_409_CONFLICT,
                )

            if not is_valid_requirement_transition(
                requirement.status,
                "service_proposed",
            ):
                return Response(
                    {"error": "invalid_transition"},
                    status=status.HTTP_409_CONFLICT,
                )

            proposal = serializer.save(requirement=requirement)

            old_status = requirement.status
            requirement.status = "service_proposed"
            requirement.save(update_fields=["status"])

            StatusChangeLog.objects.create(
                entity_type="requirement",
                entity_id=requirement.id,
                from_status=old_status,
                to_status=requirement.status,
                admin_user=request.user,
            )

        return Response(
            {
                "proposalId": str(proposal.public_id),
                "requirementReferenceId": requirement.reference_id,
                "status": requirement.status,
            },
            status=status.HTTP_201_CREATED,
        )
        



class PublicProposalDetailView(RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ServiceProposalPublicSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "proposal_id"

    queryset = ServiceProposal.objects.select_related("requirement")

