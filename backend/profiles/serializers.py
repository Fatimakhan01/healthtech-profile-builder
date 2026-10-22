from collections.abc import Mapping

from rest_framework import serializers

from .models import HealthProfile


class HealthProfileSerializer(serializers.ModelSerializer):
    is_complete = serializers.SerializerMethodField()

    class Meta:
        model = HealthProfile
        fields = (
            "full_name",
            "age_range",
            "is_complete",
            "contact_preference",
            "wellness_goals",
            "allergies",
            "emergency_contact_name",
            "emergency_contact_relationship",
            "emergency_contact_phone",
            "lifestyle_notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def get_is_complete(self, obj):
        return bool(
            obj.full_name.strip()
            and obj.age_range in HealthProfile.AgeRange.values
        )

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            writable_fields = {
                field_name
                for field_name, field in self.fields.items()
                if not field.read_only
            }
            writable_fields.add("is_complete")
            unexpected_fields = set(data) - writable_fields
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
