from django.contrib.auth import get_user_model
from rest_framework import serializers

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

