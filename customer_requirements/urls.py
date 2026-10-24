from django.urls import path

from .views import (
    RequirementCreateView,
    RequirementLookupView,
    AdminRequirementListView,
    AdminRequirementDetailView,
    AdminRequirementStatusUpdateView,
    AdminRequirementNotesUpdateView,
)

urlpatterns = [
    path("", RequirementCreateView.as_view(), name="requirement-create"),
    path("admin/", AdminRequirementListView.as_view(), name="admin-requirement-list"),
    path(
        "admin/<int:pk>/",
        AdminRequirementDetailView.as_view(),
        name="admin-requirement-detail",
    ),
    path(
        "admin/<int:pk>/status/",
        AdminRequirementStatusUpdateView.as_view(),
        name="admin-requirement-status-update",
    ),
    path(
        "admin/<int:pk>/notes/",
        AdminRequirementNotesUpdateView.as_view(),
        name="admin-requirement-notes-update",
    ),
    path("<str:ref>/", RequirementLookupView.as_view(), name="requirement-lookup"),
]