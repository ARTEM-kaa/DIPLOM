from django.db import transaction
from rest_framework import serializers

from duties.models import DutyType
from users.validators import validate_date_not_before_today
from .models import ReplacementRequest, ScheduleRule
from .models import ScheduleTemplate


class ReplacementRequestSerializer(serializers.ModelSerializer):
    """Serializer for replacement request objects."""

    class Meta:
        model = ReplacementRequest
        fields = "__all__"
        read_only_fields = [
            "id",
            "status",
            "created_at",
            "soldier_accepted_at",
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


class ScheduleTemplateSerializer(serializers.ModelSerializer):
    """Serializer for schedule templates."""

    class Meta:
        model = ScheduleTemplate
        fields = "__all__"

    def validate_rules(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("rules must be an object/dictionary.")

        all_ids: list[int] = []
        for raw_day, duty_type_ids in value.items():
            try:
                day = int(raw_day)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    f"Weekday key '{raw_day}' must be an integer from 0 to 6."
                ) from exc

            if day < 0 or day > 6:
                raise serializers.ValidationError(
                    f"Weekday key '{raw_day}' must be in range 0..6."
                )

            if not isinstance(duty_type_ids, list):
                raise serializers.ValidationError(
                    f"rules['{raw_day}'] must be a list of duty_type_id."
                )

            for duty_type_id in duty_type_ids:
                if not isinstance(duty_type_id, int):
                    raise serializers.ValidationError(
                        f"rules['{raw_day}'] contains non-integer duty_type_id."
                    )
                all_ids.append(duty_type_id)

        existing_ids = set(DutyType.objects.filter(id__in=all_ids).values_list("id", flat=True))
        missing_ids = sorted(set(all_ids) - existing_ids)
        if missing_ids:
            raise serializers.ValidationError(
                f"Unknown duty_type_id in rules: {missing_ids}."
            )

        return value

    @transaction.atomic
    def create(self, validated_data):
        instance = super().create(validated_data)
        if instance.is_default:
            ScheduleTemplate.objects.exclude(id=instance.id).update(is_default=False)
        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        updated = super().update(instance, validated_data)
        if updated.is_default:
            ScheduleTemplate.objects.exclude(id=updated.id).update(is_default=False)
        return updated


class GenerateFromTemplateSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    template_id = serializers.IntegerField(required=False)

    def validate_start_date(self, value):
        return validate_date_not_before_today(value, label="start_date")

    def validate_end_date(self, value):
        return validate_date_not_before_today(value, label="end_date")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError(
                {"detail": "start_date must be before or equal to end_date."}
            )
        return attrs

