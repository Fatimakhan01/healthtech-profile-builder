from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .models import HealthProfile


class HealthProfileModelTests(SimpleTestCase):
    def test_admin_listing_index_covers_status_and_creation_order(self):
        indexes = {index.name: index for index in HealthProfile._meta.indexes}

        self.assertIn("profiles_active_created_idx", indexes)
        self.assertEqual(
            indexes["profiles_active_created_idx"].fields,
            ["is_active", "-created_at"],
        )

    def test_profile_has_no_precise_date_of_birth_field(self):
        self.assertNotIn(
            "date_of_birth",
            {field.name for field in HealthProfile._meta.get_fields()},
        )

    def test_user_relationship_cascades_profile_deletion(self):
        user_field = HealthProfile._meta.get_field("user")

        self.assertTrue(user_field.one_to_one)
        self.assertEqual(user_field.remote_field.on_delete.__name__, "CASCADE")

    def test_partial_emergency_contact_is_invalid(self):
        profile = HealthProfile(
            full_name="Example Person",
            emergency_contact_name="Fictional Contact",
        )

        with self.assertRaises(ValidationError):
            profile.clean()
