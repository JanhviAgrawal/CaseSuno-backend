"""
Build Plan Section 9 (Page 16)
Matter Tasks Admin API Tests
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
from tasks.models import MatterTask


class MatterTasksAPITests(APITestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            name="Operations Task Admin",
            email="ops-tasks@casesuno.com",
            role="admin",
            is_active=True,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

        self.requirement = Requirement.objects.create(
            reference_id="CS-2026-00077",
            name="Vikram Seth",
            mobile="9876543210",
            email="vikram@example.com",
            city="Chennai",
            requirement_type="IP Trademark Opposition",
            description="Filing opposition against trademark application.",
            consent_given=True,
            status="converted",
        )

        self.proposal = ServiceProposal.objects.create(
            requirement=self.requirement,
            service_name="Trademark Opposition Filing",
            scope="Drafting grounds of opposition and filing at TM Registry",
            fee=Decimal("15000.00"),
            currency="INR",
            valid_until=timezone.localdate() + timedelta(days=30),
        )

        self.matter = Matter.objects.create(
            proposal=self.proposal,
            status=Matter.Status.ACTIVE,
        )

    def test_admin_can_create_task_for_matter(self):
        url = reverse("admin-matter-task-create", kwargs={"matter_id": self.matter.pk})
        due_date = str(timezone.localdate() + timedelta(days=5))
        payload = {
            "title": "Draft notice of opposition",
            "dueDate": due_date,
        }

        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["title"], "Draft notice of opposition")
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(str(response.data["dueDate"]), due_date)

        task = MatterTask.objects.get(pk=response.data["id"])
        self.assertEqual(task.matter, self.matter)

    def test_create_task_rejects_empty_title(self):
        url = reverse("admin-matter-task-create", kwargs={"matter_id": self.matter.pk})
        payload = {"title": "   "}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_update_task_status_and_due_date(self):
        task = MatterTask.objects.create(
            matter=self.matter,
            title="Initial client review",
            status=MatterTask.Status.PENDING,
        )

        url = reverse("admin-task-update", kwargs={"task_id": task.pk})
        new_due_date = str(timezone.localdate() + timedelta(days=3))
        payload = {
            "status": "in_progress",
            "dueDate": new_due_date,
        }

        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "in_progress")

        task.refresh_from_db()
        self.assertEqual(task.status, MatterTask.Status.IN_PROGRESS)
        self.assertEqual(str(task.due_date), new_due_date)

    def test_unauthenticated_request_is_rejected(self):
        unauth_client = APIClient()
        url = reverse("admin-matter-task-create", kwargs={"matter_id": self.matter.pk})
        response = unauth_client.post(url, {"title": "Test"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
