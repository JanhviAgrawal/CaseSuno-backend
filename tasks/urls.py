
from django.urls import path

from .views import AdminMatterTaskCreateView, AdminTaskUpdateView

urlpatterns = [
    path(
        "admin/matters/<int:matter_id>/tasks/",
        AdminMatterTaskCreateView.as_view(),
        name="admin-matter-task-create",
    ),
    path(
        "admin/tasks/<int:task_id>/",
        AdminTaskUpdateView.as_view(),
        name="admin-task-update",
    ),
]
