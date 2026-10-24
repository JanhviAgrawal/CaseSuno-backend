"""
Build Plan Section 7, 9 & 12 (Pages 15-16, 18-19)
Admin Matter Management & Operations Tests
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
from matters.models import Matter
from professionals.models import Professional


class MatterOperationsAPITests(APITestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            name="Operations Lead",
            email="ops-matters@casesuno.com",
            role="admin",
            is_active=True,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

        self.requirement = Requirement.objects.create(
            reference_id="CS-2026-00055",
            name="Kavita Reddy",
            mobile="9876543210",
            email="kavita@example.com",
            city="Hyderabad",
            requirement_type="Divorce Settlement Advisory",
            description="Mutual consent settlement review.",
            consent_given=True,
            status="converted",
        )

        self.proposal = ServiceProposal.objects.create(
            requirement=self.requirement,
            service_name="Divorce Settlement Advisory",
            scope="Vetting of settlement agreement",
            fee=Decimal("12000.00"),
            currency="INR",
            valid_until=timezone.localdate() + timedelta(days=30),
        )

        self.matter = Matter.objects.create(
            proposal=self.proposal,
            status=Matter.Status.ACTIVE,
            coordination_notes="Initial file assigned to family law desk.",
        )

        self.professional = Professional.objects.create(
            name="Adv. Meera Sen",
            specialism="Family & Matrimonial Law",
            contact="meera@advocates.org",
            is_active=True,
        )

    def test_admin_can_list_matters(self):
        url = reverse("admin-matter-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertGreaterEqual(response.data["count"], 1)

    def test_admin_can_view_matter_detail_with_coordination_notes(self):
        url = reverse("admin-matter-detail", kwargs={"pk": self.matter.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.matter.pk)
        self.assertEqual(response.data["serviceName"], "Divorce Settlement Advisory")
        self.assertEqual(
            response.data["coordinationNotes"],
            "Initial file assigned to family law desk.",
        )

    def test_admin_can_advance_matter_status_to_closed(self):
        url = reverse("admin-matter-status-update", kwargs={"pk": self.matter.pk})

        # active -> in_progress
        res1 = self.client.patch(url, {"status": "in_progress"}, format="json")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # in_progress -> completed
        res2 = self.client.patch(url, {"status": "completed"}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)

        # completed -> closed (sets closed_at)
        res3 = self.client.patch(url, {"status": "closed"}, format="json")
        self.assertEqual(res3.status_code, status.HTTP_200_OK)

        self.matter.refresh_from_db()
        self.assertEqual(self.matter.status, Matter.Status.CLOSED)
        self.assertIsNotNone(self.matter.closed_at)

    def test_admin_can_assign_professionals_to_matter(self):
        url = reverse("admin-matter-professionals", kwargs={"pk": self.matter.pk})
        payload = {"professional_ids": [self.professional.pk]}
        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "professionals_assigned")
        self.assertEqual(response.data["professional_ids"], [self.professional.pk])

        # Assert many-to-many relationship
        self.assertTrue(self.matter.professionals.filter(pk=self.professional.pk).exists())
