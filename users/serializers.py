from django.contrib.auth import get_user_model
from rest_framework import serializers

from .validators import (
    validate_date_not_before_today,
    validate_email_simple_field,
    validate_phone_number_field,
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user objects."""

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "military_rank",
            "platoon",
            "scientific_supervisor",
            "research_topic",
            "phone_number",
            "status",
            "status_until",
            "duty_count_this_month",
        ]
        read_only_fields = ["id", "duty_count_this_month", "role"]

    def validate_phone_number(self, value):
        return validate_phone_number_field(value)

    def validate_email(self, value):
        return validate_email_simple_field(value)

    def validate_status_until(self, value):
        return validate_date_not_before_today(value, label="status_until")

    def update(self, instance, validated_data):
        """
        Restrict fields a soldier can update on their own profile.
        """
        request = self.context.get("request")
        if request and request.user.role == getattr(User.Role, "SOLDIER", "soldier"):
            allowed_fields = {
                "username",
                "first_name",
                "last_name",
                "research_topic",
                "phone_number",
                "status",
                "status_until",
                "email",
            }
            validated_data = {
                k: v for k, v in validated_data.items() if k in allowed_fields
            }
        return super().update(instance, validated_data)


class UserStatusSerializer(serializers.ModelSerializer):
    """Serializer for updating user status."""

    class Meta:
        model = User
        fields = ["status", "status_until"]

    def validate_status_until(self, value):
        return validate_date_not_before_today(value, label="status_until")

