import secrets

from django.db import models


def generate_access_token() -> str:
    """Unguessable token used in the customer's private tracking link."""
    return secrets.token_urlsafe(24)


class Requirement(models.Model):
    """
    A customer enquiry / requirement.

    The original Build Plan pipeline (new -> contacted -> information_received ->
    reviewed -> service_proposed -> payment_pending -> converted) is kept intact.
    The website workflow adds the after-payment and closing stages
    (in_progress, forwarded, resolved, closed, rejected).
    """

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        INFORMATION_RECEIVED = (
            "information_received",
            "Information Received",
        )
        REVIEWED = "reviewed", "Reviewed"
        SERVICE_PROPOSED = "service_proposed", "Service Proposed"
        PAYMENT_PENDING = "payment_pending", "Payment Pending"
        CONVERTED = "converted", "Converted (fee paid)"
        # Website workflow stages
        IN_PROGRESS = "in_progress", "In Progress (in-house)"
        FORWARDED = "forwarded", "Forwarded to professional"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
        REJECTED = "rejected", "Not serviceable"

    class Urgency(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    class Handling(models.TextChoices):
        UNDECIDED = "undecided", "Undecided"
        IN_HOUSE = "in_house", "Managed in-house"
        LAWYER = "lawyer", "Forward to lawyer"

    class Language(models.TextChoices):
        EN = "en", "English"
        HI = "hi", "Hindi"
        GU = "gu", "Gujarati"

    reference_id = models.CharField(
        max_length=20,
        unique=True,
    )

    access_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_access_token,
        editable=False,
        help_text="Secret token for the customer's private tracking link.",
    )

    name = models.CharField(max_length=120)
    internal_notes = models.TextField(blank=True, default="")
    mobile = models.CharField(max_length=20)
    email = models.EmailField(blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")

    requirement_type = models.CharField(max_length=120)
    description = models.TextField()
    other_party = models.CharField(
        max_length=255,
        blank=True,
    )

    language = models.CharField(
        max_length=2,
        choices=Language.choices,
        default=Language.EN,
    )

    urgency = models.CharField(
        max_length=10,
        choices=Urgency.choices,
        default=Urgency.MEDIUM,
    )

    handling = models.CharField(
        max_length=12,
        choices=Handling.choices,
        default=Handling.UNDECIDED,
    )

    consent_given = models.BooleanField(default=False)

    documents = models.JSONField(default=list, blank=True)

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )

    # Platform fee requested from the customer (in paise) — mirrors the proposal fee
    fee_amount_paise = models.PositiveIntegerField(null=True, blank=True)
    fee_note = models.CharField(max_length=300, blank=True, default="")

    assigned_professional = models.ForeignKey(
        "professionals.Professional",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requirements",
    )
    share_professional_with_customer = models.BooleanField(default=False)

    reviewed_by = models.ForeignKey(
        "accounts.AdminUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_requirements",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference_id} - {self.name}"


class RequirementMessage(models.Model):
    """Conversation between the customer (tracking page) and the CASE SUNO team."""

    class Sender(models.TextChoices):
        ADMIN = "ADMIN", "CASE SUNO"
        CLIENT = "CLIENT", "Customer"

    requirement = models.ForeignKey(
        Requirement,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.CharField(max_length=10, choices=Sender.choices)
    body = models.TextField()
    read_by_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["sender", "read_by_admin"])]

    def __str__(self):
        return f"{self.sender} message on {self.requirement.reference_id}"


class RequirementNote(models.Model):
    """Internal notes — never shown to the customer."""

    requirement = models.ForeignKey(
        Requirement,
        on_delete=models.CASCADE,
        related_name="notes",
    )
    body = models.TextField()
    author = models.ForeignKey(
        "accounts.AdminUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requirement_notes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Note on {self.requirement.reference_id}"


class RequirementEvent(models.Model):
    """Activity timeline shown in the admin workspace."""

    requirement = models.ForeignKey(
        Requirement,
        on_delete=models.CASCADE,
        related_name="events",
    )
    type = models.CharField(max_length=40)
    detail = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.type} on {self.requirement.reference_id}"
