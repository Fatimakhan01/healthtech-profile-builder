from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .models import User, normalize_email


class UserModelTests(SimpleTestCase):
    def test_email_normalization_trims_and_lowercases_address(self):
        self.assertEqual(
            normalize_email("  Patient.Example@Example.COM "),
            "patient.example@example.com",
        )

    def test_model_validation_normalizes_email(self):
        user = User(email="Patient.Example@Example.COM")
        user.set_password("validation-only-password")

        user.clean_fields()
        user.clean()

        self.assertEqual(user.email, "patient.example@example.com")

    def test_model_validation_rejects_invalid_email(self):
        user = User(email="not-an-email")
        user.set_password("validation-only-password")

        with self.assertRaises(ValidationError):
            user.clean_fields()

    def test_create_user_manager_cannot_assign_admin_role(self):
        with self.assertRaisesMessage(
            ValueError,
            "Use create_superuser to create an administrator.",
        ):
            User.objects.create_user(
                "admin@example.com",
                "not-a-real-password",
                role=User.Role.ADMIN,
            )

    def test_case_insensitive_unique_constraint_is_declared(self):
        constraints = {
            constraint.name: constraint for constraint in User._meta.constraints
        }

        self.assertIn("accounts_user_email_ci_unique", constraints)
        self.assertEqual(
            str(constraints["accounts_user_email_ci_unique"].expressions[0]),
            "Lower(F(email))",
        )
