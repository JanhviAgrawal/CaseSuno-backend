
import uuid

from django.db import models


class ServiceProposal(models.Model):
    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    requirement = models.OneToOneField(
        "customer_requirements.Requirement",
        on_delete=models.PROTECT,
        related_name="proposal",
    )

    service_name = models.CharField(max_length=200)

    scope = models.TextField()

    fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    currency = models.CharField(
        max_length=3,
        default="INR",
    )

    valid_until = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.service_name} - {self.requirement.reference_id}"
