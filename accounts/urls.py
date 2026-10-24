
from django.urls import path
from .views import (
    AdminOTPRequestView,
    AdminOTPVerifyView,
    AdminMeView,
    AdminLogoutView,
)

urlpatterns = [
    path(
        "admin/login/otp/",
        AdminOTPRequestView.as_view(),
        name="admin-login-otp",
    ),
    path(
        "admin/login/",
        AdminOTPVerifyView.as_view(),
        name="admin-login",
    ),
    path(
        "admin/me/",
        AdminMeView.as_view(),
        name="admin-me",
    ),
    path(
        "admin/logout/",
        AdminLogoutView.as_view(),
        name="admin-logout",
    ),
]

