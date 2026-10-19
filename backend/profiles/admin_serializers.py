from rest_framework import serializers

from .models import HealthProfile


class AdminHealthProfileSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = HealthProfile
        fields = (
            "id",
            "user_id",
            "email",
            "full_name",
            "age_range",
            "contact_preference",
            "wellness_goals",
            "allergies",
            "emergency_contact_name",
            "emergency_contact_relationship",
            "emergency_contact_phone",
            "lifestyle_notes",
            "is_active",
            "created_at",
            "updated_at",
        )


class AdminProfileStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthProfile
        fields = ("is_active",)
