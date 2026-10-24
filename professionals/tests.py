from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from accounts.models import AdminUser
from .models import Professional


class ProfessionalAPITests(APITestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            name="Operations Lead",
            email="ops@casesuno.com",
            role="admin",
            is_active=True,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

        self.list_create_url = reverse("admin-professional-list-create")

        self.p1 = Professional.objects.create(
            name="Adv. Rajesh Kumar",
            specialism="Property & Civil Litigation",
            contact="rajesh@lawchambers.in",
            is_active=True,
        )
        self.p2 = Professional.objects.create(
            name="CA Priya Sharma",
            specialism="Corporate Taxation & Compliance",
            contact="priya@sharma-ca.in",
            is_active=False,
        )

    def test_admin_can_list_active_professionals(self):
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Default active_only=true returns only active
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Adv. Rajesh Kumar")

    def test_admin_can_list_all_professionals(self):
        response = self.client.get(self.list_create_url, {"active_only": "false"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_admin_can_create_new_professional(self):
        payload = {
            "name": "Adv. Vikram Singh",
            "specialism": "Criminal & Consumer Law",
            "contact": "vikram@advocates.in",
            "isActive": True,
        }
        response = self.client.post(self.list_create_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["name"], "Adv. Vikram Singh")
        self.assertEqual(response.data["specialism"], "Criminal & Consumer Law")

        # Verify DB
        created = Professional.objects.get(name="Adv. Vikram Singh")
        self.assertEqual(created.contact, "vikram@advocates.in")
        self.assertTrue(created.is_active)

    def test_create_rejects_empty_name(self):
        payload = {
            "name": "   ",
            "specialism": "Corporate Law",
            "contact": "test@law.in",
        }
        response = self.client.post(self.list_create_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_request_is_rejected(self):
        unauth_client = APIClient()
        response = unauth_client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
