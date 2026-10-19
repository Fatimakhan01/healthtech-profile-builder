from collections.abc import Mapping

from rest_framework import serializers

from .models import HealthProfile


class HealthProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthProfile
        fields = (
            "full_name",
            "age_range",
            "contact_preference",
            "wellness_goals",
            "allergies",
            "emergency_contact_name",
            "emergency_contact_relationship",
            "emergency_contact_phone",
            "lifestyle_notes",
        )

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unexpected_fields = set(data) - set(self.fields)
            if unexpected_fields:
                raise serializers.ValidationError(
                    {"detail": "Only health profile fields may be updated."}
                )
        return super().to_internal_value(data)

    def validate_full_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value

    def validate(self, attrs):
        contact_fields = (
            "emergency_contact_name",
            "emergency_contact_relationship",
            "emergency_contact_phone",
        )
        contact_values = [
            attrs.get(field, getattr(self.instance, field, "")) for field in contact_fields
        ]
        if any(contact_values) and not all(contact_values):
            raise serializers.ValidationError(
                {
                    "emergency_contact_name": (
                        "Provide the emergency contact name, relationship, and phone together."
                    )
                }
            )
        return attrs
