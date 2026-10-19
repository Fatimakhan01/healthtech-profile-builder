from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


phone_number_validator = RegexValidator(
    regex=r"^\+?[0-9 .()-]{7,20}$",
    message=_("Enter a phone number containing 7 to 20 permitted characters."),
)


class HealthProfile(models.Model):
    class AgeRange(models.TextChoices):
        UNDER_18 = "under_18", _("Under 18")
        FROM_18_TO_24 = "18_24", _("18-24")
        FROM_25_TO_34 = "25_34", _("25-34")
        FROM_35_TO_44 = "35_44", _("35-44")
        FROM_45_TO_54 = "45_54", _("45-54")
        FROM_55_TO_64 = "55_64", _("55-64")
        SIXTY_FIVE_AND_OVER = "65_plus", _("65 and over")
        PREFER_NOT_TO_SAY = "not_say", _("Prefer not to say")

    class ContactPreference(models.TextChoices):
        EMAIL = "email", _("Email")
        PHONE = "phone", _("Phone")
        NO_PREFERENCE = "none", _("No preference")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="health_profile",
    )
    full_name = models.CharField(max_length=150)
    age_range = models.CharField(
        max_length=10,
        choices=AgeRange.choices,
        blank=True,
    )
    contact_preference = models.CharField(
        max_length=10,
        choices=ContactPreference.choices,
        default=ContactPreference.EMAIL,
    )
    wellness_goals = models.CharField(max_length=1000, blank=True)
    allergies = models.CharField(max_length=1000, blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True)
    emergency_contact_phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[phone_number_validator],
    )
    lifestyle_notes = models.CharField(max_length=1000, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["is_active", "-created_at"],
                name="profiles_active_created_idx",
            ),
        ]
        ordering = ["-created_at"]

    def clean(self):
        self.full_name = self.full_name.strip()
        self.emergency_contact_name = self.emergency_contact_name.strip()
        self.emergency_contact_relationship = self.emergency_contact_relationship.strip()
        self.emergency_contact_phone = self.emergency_contact_phone.strip()
        emergency_contact_details = (
            self.emergency_contact_name,
            self.emergency_contact_relationship,
            self.emergency_contact_phone,
        )
        if any(emergency_contact_details) and not all(emergency_contact_details):
            raise ValidationError(
                {
                    "emergency_contact_name": _(
                        "Provide the emergency contact name, relationship, and phone together."
                    )
                }
            )

    def __str__(self):
        return self.full_name
