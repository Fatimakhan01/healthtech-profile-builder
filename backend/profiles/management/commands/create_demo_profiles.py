from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User

from profiles.models import HealthProfile, ProfileAuditEvent


DEMO_PROFILES = (
    {
        "email": "demo.member.001@example.test",
        "full_name": "Fictional Demo Member One",
        "age_range": HealthProfile.AgeRange.FROM_25_TO_34,
        "contact_preference": HealthProfile.ContactPreference.EMAIL,
        "wellness_goals": "Build a consistent walking routine.",
    },
    {
        "email": "demo.member.002@example.test",
        "full_name": "Fictional Demo Member Two",
        "age_range": HealthProfile.AgeRange.FROM_35_TO_44,
        "contact_preference": HealthProfile.ContactPreference.PHONE,
        "wellness_goals": "Practice regular stretching.",
    },
    {
        "email": "demo.member.003@example.test",
        "full_name": "Fictional Demo Member Three",
        "age_range": HealthProfile.AgeRange.PREFER_NOT_TO_SAY,
        "contact_preference": HealthProfile.ContactPreference.NO_PREFERENCE,
        "wellness_goals": "Improve sleep consistency.",
    },
)


class Command(BaseCommand):
    help = "Create fictional standard-user demo profiles without changing existing records."

    def handle(self, *args, **options):
        created = 0
        skipped = 0

        for demo_profile in DEMO_PROFILES:
            with transaction.atomic():
                if User.objects.filter(email__iexact=demo_profile["email"]).exists():
                    skipped += 1
                    continue

                user = User(
                    email=demo_profile["email"],
                    role=User.Role.STANDARD,
                )
                user.set_unusable_password()
                user.save(force_insert=True)
                profile = HealthProfile.objects.create(
                    user=user,
                    full_name=demo_profile["full_name"],
                    age_range=demo_profile["age_range"],
                    contact_preference=demo_profile["contact_preference"],
                    wellness_goals=demo_profile["wellness_goals"],
                )
                ProfileAuditEvent.objects.create(
                    actor=None,
                    action=ProfileAuditEvent.Action.CREATED,
                    profile_id=profile.pk,
                )
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created} fictional demo profile(s); "
                f"skipped {skipped} existing demo email(s)."
            )
        )
