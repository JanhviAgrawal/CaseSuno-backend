from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions.admin_auth import (
    AdminSessionAuthentication,
    IsAuthenticatedAdmin,
)
from .models import Professional
from .serializers import ProfessionalSerializer, ProfessionalCreateSerializer


class AdminProfessionalListCreateView(APIView):
    """
    Admin endpoint to list and register legal professionals (lawyers, CAs, CS).
    GET  /api/professionals/admin/
    POST /api/professionals/admin/
    Build Plan Reference: Section 4, 7 & 9 (Pages 5, 15)
    """
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def get(self, request):
        active_only = request.query_params.get("active_only", "true").lower() in ("true", "1")
        queryset = Professional.objects.all().order_by("name")
        if active_only:
            queryset = queryset.filter(is_active=True)

        serializer = ProfessionalSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ProfessionalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        professional = serializer.save()

        output_serializer = ProfessionalSerializer(professional)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class AdminProfessionalDetailView(APIView):
    """
    Admin endpoint to view and update an individual legal professional.
    GET   /api/professionals/admin/<pk>/
    PATCH /api/professionals/admin/<pk>/
    """
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def get(self, request, pk):
        professional = get_object_or_404(Professional, pk=pk)
        serializer = ProfessionalSerializer(professional)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        professional = get_object_or_404(Professional, pk=pk)
        serializer = ProfessionalSerializer(
            professional,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        updated_professional = serializer.save()
        return Response(
            ProfessionalSerializer(updated_professional).data,
            status=status.HTTP_200_OK,
        )
