from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User

from .models import HealthProfile


class CreateDemoProfilesCommandTests(TestCase):
    def test_command_creates_three_repeatable_fictional_profiles(self):
        first_output = StringIO()
        call_command("create_demo_profiles", stdout=first_output)

        self.assertIn("Created 3 fictional demo profile(s)", first_output.getvalue())
        self.assertEqual(
            User.objects.filter(email__startswith="demo.member.").count(),
            3,
        )
        self.assertEqual(
            HealthProfile.objects.filter(
                user__email__startswith="demo.member."
            ).count(),
            3,
        )

        users = list(User.objects.filter(email__startswith="demo.member."))
        self.assertTrue(all(user.role == User.Role.STANDARD for user in users))
        self.assertTrue(all(user.is_active for user in users))
        self.assertTrue(all(not user.has_usable_password() for user in users))
        original_profiles = {
            profile.user.email: (profile.full_name, profile.wellness_goals)
            for profile in HealthProfile.objects.filter(
                user__email__startswith="demo.member."
            )
        }

        second_output = StringIO()
        call_command("create_demo_profiles", stdout=second_output)

        self.assertIn("Created 0 fictional demo profile(s)", second_output.getvalue())
        self.assertIn("skipped 3 existing demo email(s)", second_output.getvalue())
        self.assertEqual(
            User.objects.filter(email__startswith="demo.member.").count(),
            3,
        )
        self.assertEqual(
            {
                profile.user.email: (profile.full_name, profile.wellness_goals)
                for profile in HealthProfile.objects.filter(
                    user__email__startswith="demo.member."
                )
            },
            original_profiles,
        )

    def test_command_does_not_modify_existing_matching_email(self):
        existing_user = User.objects.create_user(
            email="DEMO.MEMBER.001@EXAMPLE.TEST",
            password="fictional-test-password",
        )
        existing_profile = HealthProfile.objects.create(
            user=existing_user,
            full_name="Existing Fictional Owner",
            wellness_goals="Keep this existing value.",
        )
        output = StringIO()

        call_command("create_demo_profiles", stdout=output)

        existing_user.refresh_from_db()
        existing_profile.refresh_from_db()
        self.assertEqual(existing_user.email, "demo.member.001@example.test")
        self.assertEqual(existing_profile.full_name, "Existing Fictional Owner")
        self.assertEqual(
            existing_profile.wellness_goals,
            "Keep this existing value.",
        )
        self.assertEqual(
            HealthProfile.objects.filter(
                user__email__startswith="demo.member."
            ).count(),
            3,
        )
        self.assertIn("Created 2 fictional demo profile(s)", output.getvalue())
        self.assertIn("skipped 1 existing demo email(s)", output.getvalue())
