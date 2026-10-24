
from django.db import models
from django.conf import settings


class AdminUser(models.Model):

    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        ADMIN = "admin", "Admin"
        REVIEWER = "reviewer", "Reviewer"
        
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admin_profile",
        null=True,
        blank=True,
    )

    name = models.CharField(max_length=120)

    email = models.EmailField(unique=True)

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.REVIEWER,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def __str__(self):
        return f"{self.name} ({self.email})"


class AdminLoginOTP(models.Model):
    admin_user = models.ForeignKey(
        "accounts.AdminUser",
        on_delete=models.CASCADE,
        related_name="login_otps",
    )
    otp_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"OTP for {self.admin_user.email}"
    
    

class AdminSession(models.Model):
    admin_user = models.ForeignKey(
        "accounts.AdminUser",
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    token_hash = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Session for {self.admin_user.email}"

