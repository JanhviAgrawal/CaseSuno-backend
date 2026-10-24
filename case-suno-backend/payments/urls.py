
from django.urls import path

from .views import (
    CreateProposalPaymentView,
    RazorpayWebhookView,
    VerifyPaymentSignatureView,
)

urlpatterns = [
    path(
        "proposals/<uuid:proposal_id>/payment/",
        CreateProposalPaymentView.as_view(),
        name="create-proposal-payment",
    ),
    path(
        "verify/",
        VerifyPaymentSignatureView.as_view(),
        name="verify-payment",
    ),
    path(
        "webhooks/payment/",
        RazorpayWebhookView.as_view(),
        name="razorpay-webhook",
    ),
]

