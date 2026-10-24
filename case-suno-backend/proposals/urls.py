from django.urls import path
from proposals.views import AdminCreateProposalView
from .views import PublicProposalDetailView




urlpatterns = [
     path("admin/<int:pk>/proposal/", AdminCreateProposalView.as_view(),name="admin-create-proposal",),
     path("<uuid:proposal_id>/",PublicProposalDetailView.as_view(),name="public-proposal-detail",),
    
    
]