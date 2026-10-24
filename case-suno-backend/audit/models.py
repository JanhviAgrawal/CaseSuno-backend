
from django.db import models


class StatusChangeLog(models.Model):
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=100)

    from_status = models.CharField(
        max_length=30,
        blank=True,
    )
    to_status = models.CharField(max_length=30)

    admin_user = models.ForeignKey(
        "accounts.AdminUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_changes",
    )

    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"{self.entity_type} {self.entity_id}: "
            f"{self.from_status or 'None'} -> {self.to_status}"
        )
