r"""
Solution for: customer_requirements/tests.py
Build Plan Reference: Section 12, Step 2 (Pages 18-19)

Tests requirement intake API:
1. Submitting valid form returns 201 with referenceId matching ^CS-\d{4}-\d{5}$ and status 'new'.
2. Fetching submitted requirement by referenceId returns customer-safe fields.
3. Submitting with consentGiven=False is rejected with validation error (400).
4. Submitting invalid mobile is rejected with validation error (400).
"""

import re
from django.urls import reverse
from rest_framework import status
from django.core.cache import cache
from rest_framework.test import APITestCase
from customer_requirements.models import Requirement


class RequirementIntakeAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.submit_url = reverse("requirement-create")
        self.valid_payload = {
            "name": "Rohan Sharma",
            "mobile": "9876543210",
            "email": "rohan@example.com",
            "city": "Mumbai",
            "requirementType": "Property Dispute",
            "description": "Need legal assistance regarding ancestral property partition dispute.",
            "otherParty": "Opposing party details",
            "urgency": "medium",
            "consentGiven": True,
            "documents": [],
        }

    def test_requirement_submission_generates_valid_reference_id(self):
        response = self.client.post(self.submit_url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("referenceId", response.data)
        self.assertIn("status", response.data)
        self.assertEqual(response.data["status"], "new")

        ref_id = response.data["referenceId"]
        self.assertTrue(
            bool(re.match(r"^CS-\d{4}-\d{5}$", ref_id)),
            f"Reference ID {ref_id} does not match pattern ^CS-\\d{{4}}-\\d{{5}}$",
        )

        # Assert database record
        req = Requirement.objects.get(reference_id=ref_id)
        self.assertEqual(req.name, "Rohan Sharma")
        self.assertEqual(req.status, Requirement.Status.NEW)

    def test_requirement_lookup_by_reference_id(self):
        # Create a requirement first
        post_response = self.client.post(self.submit_url, self.valid_payload, format="json")
        ref_id = post_response.data["referenceId"]

        # Fetch safe public view
        lookup_url = reverse("requirement-lookup", kwargs={"ref": ref_id})
        get_response = self.client.get(lookup_url)

        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["referenceId"], ref_id)
        self.assertEqual(get_response.data["status"], "new")
        self.assertIn("createdAt", get_response.data)

        # Ensure internal notes or private admin fields are not leaked
        self.assertNotIn("internalNotes", get_response.data)
        self.assertNotIn("internal_notes", get_response.data)
        self.assertNotIn("mobile", get_response.data)

    def test_rejection_when_consent_given_is_false(self):
        payload = dict(self.valid_payload)
        payload["consentGiven"] = False

        response = self.client.post(self.submit_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("consentGiven", response.data)

    def test_rejection_when_mobile_is_invalid(self):
        payload = dict(self.valid_payload)
        payload["mobile"] = "12345"  # not 10 digits and does not start with 6-9

        response = self.client.post(self.submit_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("mobile", response.data)

    def test_lookup_nonexistent_reference_returns_404(self):
        lookup_url = reverse("requirement-lookup", kwargs={"ref": "CS-2026-99999"})
        response = self.client.get(lookup_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data.get("error"), "not_found")
