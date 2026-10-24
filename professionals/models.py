from django.db import models


class Professional(models.Model):
    """A verified lawyer / CA / professional in the CASE SUNO referral network."""

    name = models.CharField(max_length=120)

    specialism = models.CharField(max_length=160)

    # Legacy free-text contact field (kept for the Build Plan API); mirrors phone/email.
    contact = models.CharField(max_length=255, blank=True, default="")

    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.contact:
            self.contact = " / ".join(v for v in (self.phone, self.email) if v)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.specialism}"
