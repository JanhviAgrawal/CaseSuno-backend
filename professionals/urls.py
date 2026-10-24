from django.urls import path
from .views import (
    AdminProfessionalListCreateView,
    AdminProfessionalDetailView,
)

urlpatterns = [
    path(
        "admin/",
        AdminProfessionalListCreateView.as_view(),
        name="admin-professional-list-create",
    ),
    path(
        "admin/<int:pk>/",
        AdminProfessionalDetailView.as_view(),
        name="admin-professional-detail",
    ),
]