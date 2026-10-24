
from locust import HttpUser, task, between


class RequirementIntakeLoadTestUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(3)
    def submit_requirement(self):
        payload = {
            "name": "Load Test Customer",
            "mobile": "9876543210",
            "email": "loadtest@example.com",
            "city": "Mumbai",
            "requirementType": "Property Dispute",
            "description": "Burst load test to confirm rate limiting enforcement.",
            "urgency": "medium",
            "consentGiven": True,
            "documents": [],
        }
        with self.client.post("/api/requirements/", json=payload, catch_response=True) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 429:
                # 429 Too Many Requests indicates rate limiter is functioning properly under burst
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(1)
    def health_check(self):
        self.client.get("/health/")
