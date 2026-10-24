"""
Build Plan Section 12, Step 3 (Pages 18-19)
Integration test review-to-proposal:
Move requirement through every status; confirm the proposal endpoint returns 409 until reviewed is reached.
"""

from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from accounts.models import AdminUser
from customer_requirements.models import Requirement
from proposals.models import ServiceProposal


class ReviewToProposalIntegrationTests(APITestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            name="Reviewer Admin",
            email="reviewer@casesuno.com",
            role="reviewer",
            is_active=True,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

        self.requirement = Requirement.objects.create(
            reference_id="CS-2026-00099",
            name="Sunita Rao",
            mobile="9876543210",
            email="sunita@example.com",
            city="Bengaluru",
            requirement_type="Commercial Lease Review",
            description="Review of lease agreement for commercial property.",
            urgency="high",
            consent_given=True,
            status=Requirement.Status.NEW,
        )

        self.proposal_url = reverse(
            "admin-create-proposal",
            kwargs={"pk": self.requirement.pk},
        )

        self.proposal_payload = {
            "serviceName": "Commercial Lease Drafting & Advisory",
            "scope": "Clause-by-clause lease vetting and risk opinion",
            "fee": "7500.00",
            "currency": "INR",
            "validUntil": str(timezone.localdate() + timedelta(days=14)),
        }

    def test_proposal_returns_409_until_reviewed_is_reached(self):
        # 1. At status 'new': proposal creation must be rejected with 409 Conflict
        res_new = self.client.post(self.proposal_url, self.proposal_payload, format="json")
        self.assertEqual(res_new.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res_new.data.get("error"), "invalid_transition")

        # 2. Advance to 'contacted': proposal creation must still return 409
        self.requirement.status = Requirement.Status.CONTACTED
        self.requirement.save()
        res_contacted = self.client.post(self.proposal_url, self.proposal_payload, format="json")
        self.assertEqual(res_contacted.status_code, status.HTTP_409_CONFLICT)

        # 3. Advance to 'information_received': proposal creation must still return 409
        self.requirement.status = Requirement.Status.INFORMATION_RECEIVED
        self.requirement.save()
        res_info = self.client.post(self.proposal_url, self.proposal_payload, format="json")
        self.assertEqual(res_info.status_code, status.HTTP_409_CONFLICT)

        # 4. Advance to 'reviewed': proposal creation must now SUCCEED with 201 Created
        self.requirement.status = Requirement.Status.REVIEWED
        self.requirement.save()
        res_reviewed = self.client.post(self.proposal_url, self.proposal_payload, format="json")
        self.assertEqual(res_reviewed.status_code, status.HTTP_201_CREATED)
        self.assertIn("proposalId", res_reviewed.data)
        self.assertEqual(res_reviewed.data["status"], "service_proposed")

        # Confirm requirement status in database updated to service_proposed
        self.requirement.refresh_from_db()
        self.assertEqual(self.requirement.status, Requirement.Status.SERVICE_PROPOSED)

        # Confirm OneToOne proposal exists
        proposal = ServiceProposal.objects.get(requirement=self.requirement)
        self.assertEqual(str(proposal.public_id), res_reviewed.data["proposalId"])
        self.assertEqual(proposal.fee, Decimal("7500.00"))

        # 5. Attaching a second proposal to the same requirement returns 409 Conflict
        res_dup = self.client.post(self.proposal_url, self.proposal_payload, format="json")
        self.assertEqual(res_dup.status_code, status.HTTP_409_CONFLICT)

    def test_customer_public_proposal_lookup(self):
        # Setup proposal at reviewed
        self.requirement.status = Requirement.Status.REVIEWED
        self.requirement.save()
        res = self.client.post(self.proposal_url, self.proposal_payload, format="json")
        public_id = res.data["proposalId"]

        # Public unauthenticated client views proposal
        public_client = APIClient()
        lookup_url = reverse("public-proposal-detail", kwargs={"proposal_id": public_id})
        lookup_res = public_client.get(lookup_url)

        self.assertEqual(lookup_res.status_code, status.HTTP_200_OK)
        self.assertEqual(lookup_res.data["serviceName"], "Commercial Lease Drafting & Advisory")
        self.assertIn("expired", lookup_res.data)
        self.assertFalse(lookup_res.data["expired"])
