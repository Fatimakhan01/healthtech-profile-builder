from collections.abc import Mapping

from rest_framework import serializers

from .models import WorkflowJob


class EnqueueWorkflowJobSerializer(serializers.Serializer):
    job_type = serializers.ChoiceField(choices=WorkflowJob.JobType.choices)

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError("Expected a JSON object.")
        unexpected = set(data) - {"job_type"}
        if unexpected:
            raise serializers.ValidationError(
                {"detail": "Only job_type may be provided."}
            )
        return super().to_internal_value(data)


class WorkflowJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowJob
        fields = (
            "id",
            "job_type",
            "status",
            "attempt_count",
            "max_attempts",
            "duration_ms",
            "result",
            "failure_code",
            "created_at",
            "started_at",
            "finished_at",
        )
        read_only_fields = fields
