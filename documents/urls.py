"""
Solution for: documents/urls.py
Build Plan Reference: Section 6, 8 & 9 (Pages 8, 16)

Registers:
1. POST /api/documents/upload/ (Public customer pre-submission document upload)
2. POST /api/documents/admin/matters/<id>/documents/ (Admin matter document upload)
3. GET  /api/documents/admin/matters/<id>/documents/<doc_id>/download/ (Admin presigned download URL)
"""

from django.urls import path
from .views import (
    CustomerDocumentUploadView,
    AdminMatterDocumentUploadView,
    AdminMatterDocumentDownloadURLView,
)

urlpatterns = [
    path(
        "upload/",
        CustomerDocumentUploadView.as_view(),
        name="customer-document-upload",
    ),
    path(
        "admin/matters/<int:pk>/documents/",
        AdminMatterDocumentUploadView.as_view(),
        name="admin-matter-document-upload",
    ),
    path(
        "admin/matters/<int:pk>/documents/<int:document_id>/download/",
        AdminMatterDocumentDownloadURLView.as_view(),
        name="admin-matter-document-download-url",
    ),
]
