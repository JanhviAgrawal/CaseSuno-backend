
from rest_framework import serializers
from .models import Matter
from professionals.models import Professional
from tasks.models import MatterTask
from documents.models import MatterDocument


class ProfessionalBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Professional
        fields = ["id", "name", "specialism", "contact"]


class MatterTaskBriefSerializer(serializers.ModelSerializer):
    dueDate = serializers.DateField(source="due_date", read_only=True)

    class Meta:
        model = MatterTask
        fields = ["id", "title", "status", "dueDate"]


class MatterDocumentBriefSerializer(serializers.ModelSerializer):
    uploadedBy = serializers.CharField(source="uploaded_by", read_only=True)
    uploadedAt = serializers.DateTimeField(source="uploaded_at", read_only=True)
    downloadEndpoint = serializers.SerializerMethodField()

    class Meta:
        model = MatterDocument
        fields = ["id", "uploadedBy", "uploadedAt", "downloadEndpoint"]

    def get_downloadEndpoint(self, obj):
        return f"/api/matters/admin/{obj.matter_id}/documents/{obj.pk}/download/"


class AdminMatterListSerializer(serializers.ModelSerializer):
    proposalId = serializers.UUIDField(source="proposal.public_id", read_only=True)
    referenceId = serializers.CharField(source="proposal.requirement.reference_id", read_only=True)
    openedAt = serializers.DateTimeField(source="opened_at", read_only=True)
    closedAt = serializers.DateTimeField(source="closed_at", read_only=True)

    class Meta:
        model = Matter
        fields = [
            "id",
            "proposalId",
            "referenceId",
            "status",
            "openedAt",
            "closedAt",
        ]


class AdminMatterDetailSerializer(serializers.ModelSerializer):
    proposalId = serializers.UUIDField(source="proposal.public_id", read_only=True)
    referenceId = serializers.CharField(source="proposal.requirement.reference_id", read_only=True)
    serviceName = serializers.CharField(source="proposal.service_name", read_only=True)
    coordinationNotes = serializers.CharField(source="coordination_notes", required=False)
    openedAt = serializers.DateTimeField(source="opened_at", read_only=True)
    closedAt = serializers.DateTimeField(source="closed_at", read_only=True)
    professionals = ProfessionalBriefSerializer(many=True, read_only=True)
    tasks = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = Matter
        fields = [
            "id",
            "proposalId",
            "referenceId",
            "serviceName",
            "status",
            "coordinationNotes",
            "openedAt",
            "closedAt",
            "professionals",
            "documents",
            "tasks",
        ]

    def get_tasks(self, obj):
        tasks = MatterTask.objects.filter(matter=obj).order_by("due_date", "pk")
        return MatterTaskBriefSerializer(tasks, many=True).data

    def get_documents(self, obj):
        docs = MatterDocument.objects.filter(matter=obj).order_by("-uploaded_at")
        return MatterDocumentBriefSerializer(docs, many=True).data


class AdminMatterStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Matter.Status.choices)
    coordinationNotes = serializers.CharField(
        source="coordination_notes",
        required=False,
        allow_blank=True,
    )
