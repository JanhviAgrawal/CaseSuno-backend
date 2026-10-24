from django.urls import path

from . import views

urlpatterns = [
    # Public (called by the casesuno.in website server)
    path("enquiries/", views.EnquiryCreateView.as_view(), name="web-enquiry-create"),
    path("track-lookup/", views.TrackLookupView.as_view(), name="web-track-lookup"),
    path("track/<str:token>/", views.TrackDetailView.as_view(), name="web-track-detail"),
    path("track/<str:token>/messages/", views.TrackMessageView.as_view(), name="web-track-message"),
    path("payments/create-order/", views.CreateOrderView.as_view(), name="web-payment-create-order"),
    path("payments/verify/", views.VerifyPaymentView.as_view(), name="web-payment-verify"),
    # Admin panel
    path("admin/login/", views.AdminLoginView.as_view(), name="web-admin-login"),
    path("admin/logout/", views.AdminLogoutView.as_view(), name="web-admin-logout"),
    path("admin/me/", views.AdminMeView.as_view(), name="web-admin-me"),
    path("admin/dashboard/", views.AdminDashboardView.as_view(), name="web-admin-dashboard"),
    path("admin/enquiries/", views.AdminEnquiryListView.as_view(), name="web-admin-enquiries"),
    path("admin/enquiries/<int:pk>/", views.AdminEnquiryDetailView.as_view(), name="web-admin-enquiry"),
    path("admin/enquiries/<int:pk>/messages/", views.AdminEnquiryMessageView.as_view(), name="web-admin-enquiry-messages"),
    path("admin/enquiries/<int:pk>/notes/", views.AdminEnquiryNoteView.as_view(), name="web-admin-enquiry-notes"),
    path(
        "admin/enquiries/<int:pk>/request-payment/",
        views.AdminRequestPaymentView.as_view(),
        name="web-admin-enquiry-request-payment",
    ),
    path("admin/lawyers/", views.AdminLawyerListView.as_view(), name="web-admin-lawyers"),
    path("admin/lawyers/<int:pk>/", views.AdminLawyerDetailView.as_view(), name="web-admin-lawyer"),
    path("admin/payments/", views.AdminPaymentListView.as_view(), name="web-admin-payments"),
]
