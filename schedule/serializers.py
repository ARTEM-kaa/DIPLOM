from rest_framework import serializers

from .models import ReplacementRequest, ScheduleRule


class ReplacementRequestSerializer(serializers.ModelSerializer):
    """Serializer for replacement request objects."""

    class Meta:
        model = ReplacementRequest
        fields = "__all__"
        read_only_fields = [
            "id",
            "status",
            "created_at",
            "processed_at",
            "processed_by",
            "requester",
        ]


class ReplacementRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating replacement requests."""

    class Meta:
        model = ReplacementRequest
        fields = ["duty_instance", "requested_replacement", "reason"]


class ScheduleRuleSerializer(serializers.ModelSerializer):
    """Serializer for schedule rules."""

    class Meta:
        model = ScheduleRule
        fields = "__all__"

