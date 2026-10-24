
from django.urls import path

from .views import (
    AdminMatterListView,
    AdminMatterDetailView,
    AdminMatterStatusUpdateView,
    AdminMatterNotesUpdateView,
    AdminMatterProfessionalsView,
    CustomerMatterTrackingView,
)

from documents.views import (
    AdminMatterDocumentUploadView,
    AdminMatterDocumentDownloadURLView,
)

urlpatterns = [
    path(
        "tracking/<str:ref>/",
        CustomerMatterTrackingView.as_view(),
        name="customer-matter-tracking",
    ),
    path(
        "admin/",
        AdminMatterListView.as_view(),
        name="admin-matter-list",
    ),

    path(
        "admin/<int:pk>/",
        AdminMatterDetailView.as_view(),
        name="admin-matter-detail",
    ),
    path(
        "admin/<int:pk>/status/",
        AdminMatterStatusUpdateView.as_view(),
        name="admin-matter-status-update",
    ),
    path(
        "admin/<int:pk>/notes/",
        AdminMatterNotesUpdateView.as_view(),
        name="admin-matter-notes-update",
    ),

    path(
        "admin/<int:pk>/professionals/",
        AdminMatterProfessionalsView.as_view(),
        name="admin-matter-professionals",
    ),
    path(
        "admin/<int:pk>/documents/",
        AdminMatterDocumentUploadView.as_view(),
        name="admin-matter-document-upload",
    ),
    path(
        "admin/<int:pk>/documents/<int:document_id>/download/",
        AdminMatterDocumentDownloadURLView.as_view(),
        name="admin-matter-document-download-url",
    ),
]
