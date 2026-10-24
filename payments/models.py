from django.db import models

# Create your models here.

from django.db import models


class Payment(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    proposal = models.OneToOneField(
        "proposals.ServiceProposal",
        on_delete=models.PROTECT,
        related_name="payment",
    )

    gateway_order_id = models.CharField(
        max_length=100,
        unique=True,
    )

    gateway_payment_id = models.CharField(
        max_length=100,
        blank=True,
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.gateway_order_id} - {self.status}"
