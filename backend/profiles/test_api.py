from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User

from .models import HealthProfile


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

    def test_incomplete_emergency_contact_is_rejected(self):
        response = self.client.patch(
            self.profile_url,
            {"emergency_contact_name": "Fictional Contact"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("emergency_contact_name", response.data)

    def test_protected_profile_fields_are_rejected(self):
        for payload in (
            {"user": self.user.pk},
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
