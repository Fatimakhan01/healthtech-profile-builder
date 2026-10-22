from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User

from .models import HealthProfile, ProfileAuditEvent


class CurrentHealthProfileApiTests(APITestCase):
    profile_url = "/api/profiles/me/"

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.profile = HealthProfile.objects.create(
            user=self.user,
            full_name="Example Owner",
        )
        self.authenticate_as(self.user)

    def authenticate_as(self, user):
        token = AccessToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_current_user_can_retrieve_own_profile(self):
        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["full_name"], "Example Owner")
        self.assertFalse(response.data["is_complete"])
        self.assertEqual(response.data["contact_preference"], "email")
        self.assertEqual(
            parse_datetime(response.data["created_at"]),
            self.profile.created_at,
        )
        self.assertEqual(
            parse_datetime(response.data["updated_at"]),
            self.profile.updated_at,
        )
        self.assertNotIn("user", response.data)
        self.assertNotIn("is_active", response.data)
        self.assertNotIn("password", response.data)

    def test_complete_profile_is_reported_as_complete(self):
        response = self.client.patch(
            self.profile_url,
            {"age_range": "25_34"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_complete"])

    def test_blank_full_name_is_reported_as_incomplete(self):
        self.profile.full_name = " "
        self.profile.save(update_fields=["full_name"])

        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_complete"])

    def test_prefer_not_to_say_age_range_counts_as_complete(self):
        response = self.client.patch(
            self.profile_url,
            {"age_range": HealthProfile.AgeRange.PREFER_NOT_TO_SAY},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_complete"])

    def test_current_user_can_update_permitted_profile_fields(self):
        response = self.client.patch(
            self.profile_url,
            {
                "full_name": "Updated Owner",
                "age_range": "25_34",
                "wellness_goals": "Improve daily activity",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(
            parse_datetime(response.data["created_at"]),
            self.profile.created_at,
        )
        self.assertEqual(
            parse_datetime(response.data["updated_at"]),
            self.profile.updated_at,
        )
        self.assertEqual(self.profile.full_name, "Updated Owner")
        self.assertEqual(self.profile.age_range, "25_34")
        self.assertEqual(self.profile.wellness_goals, "Improve daily activity")
        event = ProfileAuditEvent.objects.get()
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.action, ProfileAuditEvent.Action.UPDATED)
        self.assertEqual(event.profile_id, self.profile.pk)

    def test_patch_ignores_returned_completion_field_without_allowing_override(self):
        response = self.client.patch(
            self.profile_url,
            {
                "full_name": "Updated Owner",
                "age_range": "25_34",
                "is_complete": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_complete"])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.full_name, "Updated Owner")
        self.assertEqual(self.profile.age_range, "25_34")

    def test_invalid_profile_choices_and_phone_are_rejected(self):
        for payload in (
            {"age_range": "not-a-choice"},
            {"contact_preference": "carrier-pigeon"},
            {"emergency_contact_phone": "not-a-phone"},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(
                    self.profile_url,
                    payload,
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(ProfileAuditEvent.objects.exists())

    def test_incomplete_emergency_contact_is_rejected(self):
        response = self.client.patch(
            self.profile_url,
            {"emergency_contact_name": "Fictional Contact"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("emergency_contact_name", response.data)
        self.assertFalse(ProfileAuditEvent.objects.exists())

    def test_protected_profile_fields_are_rejected(self):
        for payload in (
            {"user": self.user.pk},
            {"role": "admin"},
            {"is_active": False},
            {"created_at": "2020-01-01T00:00:00Z"},
            {"updated_at": "2020-01-01T00:00:00Z"},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(
                    self.profile_url,
                    payload,
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_active)
        self.assertEqual(self.profile.full_name, "Example Owner")

    def test_anonymous_request_is_rejected(self):
        self.client.credentials()

        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_delete_own_profile_without_deleting_account(self):
        response = self.client.delete(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(HealthProfile.objects.filter(pk=self.profile.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        event = ProfileAuditEvent.objects.get()
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.action, ProfileAuditEvent.Action.DELETED)
        self.assertEqual(event.profile_id, self.profile.pk)

        missing_response = self.client.delete(self.profile_url)

        self.assertEqual(missing_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_user_cannot_delete_profile(self):
        self.client.credentials()

        response = self.client.delete(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(HealthProfile.objects.filter(pk=self.profile.pk).exists())

    def test_delete_cannot_target_another_users_profile(self):
        owner_profile_id = self.profile.pk
        other_user = User.objects.create_user(
            email="other@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.authenticate_as(other_user)

        response = self.client.delete(
            f"{self.profile_url}?profile_id={owner_profile_id}"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(
            HealthProfile.objects.filter(pk=owner_profile_id, user=self.user).exists()
        )
        self.assertTrue(User.objects.filter(pk=other_user.pk).exists())

    def test_user_can_recreate_deleted_profile(self):
        self.client.delete(self.profile_url)

        response = self.client.post(
            self.profile_url,
            {
                "full_name": "Recreated Owner",
                "age_range": "25_34",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["full_name"], "Recreated Owner")
        self.assertTrue(response.data["is_complete"])
        profile = HealthProfile.objects.get(user=self.user)
        event = ProfileAuditEvent.objects.get(
            action=ProfileAuditEvent.Action.CREATED
        )
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.action, ProfileAuditEvent.Action.CREATED)
        self.assertEqual(event.profile_id, profile.pk)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(
            HealthProfile.objects.filter(
                user=self.user,
                full_name="Recreated Owner",
            ).exists()
        )

    def test_recreate_is_rejected_when_profile_already_exists(self):
        response = self.client.post(
            self.profile_url,
            {"full_name": "Duplicate Owner"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            HealthProfile.objects.filter(user=self.user).count(),
            1,
        )
        self.assertFalse(ProfileAuditEvent.objects.exists())

    def test_audit_event_stores_only_actor_action_profile_id_and_timestamp(self):
        self.client.patch(
            self.profile_url,
            {
                "allergies": "sensitive allergy value",
                "emergency_contact_name": "Sensitive Contact",
                "emergency_contact_relationship": "Friend",
                "emergency_contact_phone": "555-555-5555",
            },
            format="json",
        )

        event = ProfileAuditEvent.objects.get()
        self.assertEqual(
            {field.name for field in event._meta.fields},
            {"id", "actor", "action", "profile_id", "created_at"},
        )
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.action, ProfileAuditEvent.Action.UPDATED)
        self.assertEqual(event.profile_id, self.profile.pk)

    def test_profile_routes_are_scoped_to_the_authenticated_user(self):
        other_user = User.objects.create_user(
            email="other@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        other_profile = HealthProfile.objects.create(
            user=other_user,
            full_name="Other Owner",
        )
        self.authenticate_as(other_user)

        get_response = self.client.get(
            f"{self.profile_url}?user={self.user.pk}"
        )
        patch_response = self.client.patch(
            self.profile_url,
            {"user": self.user.pk, "full_name": "Unauthorized change"},
            format="json",
        )

        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["full_name"], "Other Owner")
        self.assertEqual(patch_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.profile.refresh_from_db()
        other_profile.refresh_from_db()
        self.assertEqual(self.profile.full_name, "Example Owner")
        self.assertEqual(other_profile.full_name, "Other Owner")

    def test_admin_role_cannot_use_standard_profile_endpoint(self):
        admin = User.objects.create_superuser(
            email="admin@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.authenticate_as(admin)

        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
