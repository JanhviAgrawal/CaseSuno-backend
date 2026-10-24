
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from accounts.models import AdminUser
from .models import StatusChangeLog


class AdminAuditLogAPITests(APITestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            name="Audit Test Admin",
            email="audit-test@example.com",
            role="super_admin",
            is_active=True,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

        self.url = reverse("admin-audit-log-list")

        StatusChangeLog.objects.create(
            entity_type="requirement",
            entity_id="CS-2026-00001",
            from_status="new",
            to_status="contacted",
            admin_user=self.admin,
        )

        StatusChangeLog.objects.create(
            entity_type="matter",
            entity_id="1",
            from_status="active",
            to_status="in_progress",
            admin_user=self.admin,
        )

    def test_admin_can_list_audit_logs(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 2)

    def test_filter_by_entity_type(self):
        response = self.client.get(
            self.url,
            {"entity_type": "requirement"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["entityType"],
            "requirement",
        )

    def test_filter_by_entity_id(self):
        response = self.client.get(
            self.url,
            {"entity_id": "1"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["entityId"],
            "1",
        )

    def test_limit_rejects_non_integer(self):
        response = self.client.get(self.url, {"limit": "abc"})

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(response.data["error"], "invalid_limit")

    def test_limit_rejects_values_outside_range(self):
        for limit in ("0", "101"):
            with self.subTest(limit=limit):
                response = self.client.get(
                    self.url,
                    {"limit": limit},
                )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertIn(
            response.status_code,
            (
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ),
        )

    def test_audit_endpoint_is_read_only(self):
        response = self.client.post(
            self.url,
            {"entity_type": "requirement"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
