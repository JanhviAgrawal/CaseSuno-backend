
from django.db import models


class MatterDocument(models.Model):
    matter = models.ForeignKey(
        "matters.Matter",
        on_delete=models.CASCADE,
        related_name="documents",
    )

    file_key = models.CharField(max_length=500)
    uploaded_by = models.CharField(max_length=120)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Document #{self.pk} - Matter #{self.matter_id}"
