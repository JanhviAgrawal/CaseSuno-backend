
from django.db import models


class Matter(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        IN_PROGRESS = "in_progress", "In Progress"
        AWAITING_CUSTOMER = "awaiting_customer", "Awaiting Customer"
        COMPLETED = "completed", "Completed"
        CLOSED = "closed", "Closed"

    proposal = models.OneToOneField(
        "proposals.ServiceProposal",
        on_delete=models.PROTECT,
        related_name="matter",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    professionals = models.ManyToManyField(
        "professionals.Professional",
        blank=True,
        related_name="matters",
        db_table="matter_professional",
    )

    coordination_notes = models.TextField(
        blank=True,
        default="",
        help_text="Internal operational notes and coordination details between assigned team and professionals.",
    )

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Matter #{self.pk} - {self.status}"
