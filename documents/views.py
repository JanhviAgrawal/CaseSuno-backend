"""
Solution for: documents/views.py
Build Plan Reference: Section 6, 8, 9 & 10 (Pages 8, 16)

Changes Made:
1. Retained AdminMatterDocumentUploadView and AdminMatterDocumentDownloadURLView.
2. Added CustomerDocumentUploadView:
   Allows public customers to upload attachment evidence (.pdf, .jpg, .png, .docx <= 10MB)
   prior to submitting the requirement intake form.
   Performs size validation, file type signature checks, ClamAV virus scanning,
   uploads to private S3 storage under prefix 'requirements/uploads/', and returns the S3 key.
   Rate-limited with AnonRateThrottle to prevent abuse.
"""

import uuid
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from common.permissions.admin_auth import (
    AdminSessionAuthentication,
    IsAuthenticatedAdmin,
)
from matters.models import Matter
from .models import MatterDocument
from .services.storage import (
    MAX_FILE_SIZE,
    DocumentServiceUnavailable,
    InvalidDocument,
    create_presigned_download_url,
    delete_document,
    get_s3_client,
    scan_for_virus,
    upload_document,
    validate_document,
)


class CustomerDocumentUploadView(APIView):
    """
    Public rate-limited document upload endpoint for customers submitting enquiries.
    Returns the uploaded S3 object key to be included in POST /api/requirements/.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded_file = request.FILES.get("file")

        if uploaded_file is None:
            return Response(
                {"error": "file_required", "message": "No file was attached in the request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if uploaded_file.size > MAX_FILE_SIZE:
            return Response(
                {"error": "file_too_large", "message": "File exceeds the maximum allowed size of 10 MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = uploaded_file.read(MAX_FILE_SIZE + 1)

        try:
            extension, content_type = validate_document(
                uploaded_file.name,
                data,
            )

            # Scan with ClamAV before uploading to S3
            scan_for_virus(data)

            # Store in S3 with a unique UUID key
            s3_client = get_s3_client()
            from django.conf import settings
            import io

            file_key = f"requirements/uploads/{uuid.uuid4().hex}{extension}"

            s3_client.upload_fileobj(
                io.BytesIO(data),
                settings.S3_BUCKET,
                file_key,
                ExtraArgs={
                    "ContentType": content_type,
                    "ContentDisposition": "attachment",
                },
            )

        except InvalidDocument as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DocumentServiceUnavailable as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "fileKey": file_key,
                "filename": uploaded_file.name,
                "message": "File successfully uploaded and scanned.",
            },
            status=status.HTTP_201_CREATED,
        )


class AdminMatterDocumentUploadView(APIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        matter = get_object_or_404(Matter, pk=pk)

        uploaded_file = request.FILES.get("file")

        if uploaded_file is None:
            return Response(
                {"error": "file_required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if uploaded_file.size > MAX_FILE_SIZE:
            return Response(
                {"error": "file_too_large"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = uploaded_file.read(MAX_FILE_SIZE + 1)

        try:
            extension, content_type = validate_document(
                uploaded_file.name,
                data,
            )

            scan_for_virus(data)

            file_key = upload_document(
                matter.pk,
                extension,
                content_type,
                data,
            )

        except InvalidDocument as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except DocumentServiceUnavailable as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            with transaction.atomic():
                document = MatterDocument.objects.create(
                    matter=matter,
                    file_key=file_key,
                    uploaded_by=str(request.user),
                )
        except Exception:
            try:
                delete_document(file_key)
            except Exception:
                pass
            raise

        return Response(
            {
                "message": "document_uploaded",
                "id": document.pk,
                "matter_id": matter.pk,
                "uploaded_by": document.uploaded_by,
                "uploaded_at": document.uploaded_at,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminMatterDocumentDownloadURLView(APIView):
    authentication_classes = [AdminSessionAuthentication]
    permission_classes = [IsAuthenticatedAdmin]

    def get(self, request, pk, document_id):
        matter = get_object_or_404(Matter, pk=pk)

        document = get_object_or_404(
            MatterDocument,
            pk=document_id,
            matter=matter,
        )

        try:
            download_url = create_presigned_download_url(
                document.file_key,
                expires_in=300,
            )
        except DocumentServiceUnavailable as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "document_id": document.pk,
                "matter_id": matter.pk,
                "download_url": download_url,
                "expires_in_seconds": 300,
            },
            status=status.HTTP_200_OK,
        )
