from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from accounts.models import User

from .models import HealthProfile, ProfileAuditEvent


class AdminProfileListApiTests(APITestCase):
    profiles_url = "/api/admin/profiles/"
    status_url = "/api/admin/profiles/{}/status/"

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.client.force_login(self.admin)
        self.create_profile("alex@example.com", "Alex Example", True)
        self.create_profile("blair@example.com", "Blair Example", False)
        self.create_profile("casey@example.com", "Casey Example", True)

    def create_profile(self, email, full_name, is_active):
        user = User.objects.create_user(
            email=email,
            password="A-strong-but-not-real-password-834!",
        )
        return HealthProfile.objects.create(
            user=user,
            full_name=full_name,
            is_active=is_active,
        )

    def test_admin_can_list_profiles_with_bounded_pagination(self):
        response = self.client.get(f"{self.profiles_url}?page_size=2")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])
        self.assertIn("email", response.data["results"][0])
        self.assertNotIn("password", response.data["results"][0])

    def test_admin_can_search_profile_name_and_email(self):
        name_response = self.client.get(
            f"{self.profiles_url}?search=Blair"
        )
        email_response = self.client.get(
            f"{self.profiles_url}?search=casey@example.com"
        )

        self.assertEqual(name_response.data["count"], 1)
        self.assertEqual(name_response.data["results"][0]["full_name"], "Blair Example")
        self.assertEqual(email_response.data["count"], 1)
        self.assertEqual(email_response.data["results"][0]["email"], "casey@example.com")

    def test_admin_can_filter_active_status(self):
        response = self.client.get(f"{self.profiles_url}?active=false")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertFalse(response.data["results"][0]["is_active"])

    def test_search_status_filter_and_pagination_work_together(self):
        first_page = self.client.get(
            f"{self.profiles_url}?search=Example&active=true&page=1&page_size=1"
        )
        second_page = self.client.get(
            f"{self.profiles_url}?search=Example&active=true&page=2&page_size=1"
        )

        self.assertEqual(first_page.status_code, status.HTTP_200_OK)
        self.assertEqual(first_page.data["count"], 2)
        self.assertEqual(len(first_page.data["results"]), 1)
        self.assertIsNotNone(first_page.data["next"])
        self.assertTrue(first_page.data["results"][0]["is_active"])

        self.assertEqual(second_page.status_code, status.HTTP_200_OK)
        self.assertEqual(second_page.data["count"], 2)
        self.assertEqual(len(second_page.data["results"]), 1)
        self.assertIsNotNone(second_page.data["previous"])
        self.assertTrue(second_page.data["results"][0]["is_active"])
        self.assertNotEqual(
            first_page.data["results"][0]["id"],
            second_page.data["results"][0]["id"],
        )

    def test_invalid_active_filter_is_rejected(self):
        response = self.client.get(f"{self.profiles_url}?active=sometimes")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_user_cannot_list_profiles(self):
        self.client.logout()

        response = self.client.get(self.profiles_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_standard_user_session_cannot_list_profiles(self):
        standard_user = User.objects.create_user(
            email="standard@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.client.force_login(standard_user)

        response = self.client.get(self.profiles_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_deactivate_and_reactivate_profile_without_deleting_data(self):
        profile = HealthProfile.objects.get(user__email="alex@example.com")

        deactivate_response = self.client.patch(
            self.status_url.format(profile.pk),
            {"is_active": False},
            format="json",
        )

        self.assertEqual(deactivate_response.status_code, status.HTTP_200_OK)
        self.assertFalse(deactivate_response.data["is_active"])
        profile.refresh_from_db()
        self.assertFalse(profile.is_active)
        self.assertEqual(ProfileAuditEvent.objects.count(), 1)
        self.assertEqual(
            ProfileAuditEvent.objects.get().action,
            ProfileAuditEvent.Action.DEACTIVATED,
        )
        self.assertTrue(profile.user.is_active)
        self.assertTrue(
            HealthProfile.objects.filter(pk=profile.pk).exists()
        )

        reactivate_response = self.client.patch(
            self.status_url.format(profile.pk),
            {"is_active": True},
            format="json",
        )

        self.assertEqual(reactivate_response.status_code, status.HTTP_200_OK)
        self.assertTrue(reactivate_response.data["is_active"])
        profile.refresh_from_db()
        self.assertTrue(profile.is_active)
        self.assertEqual(ProfileAuditEvent.objects.count(), 2)
        events = list(ProfileAuditEvent.objects.order_by("created_at"))
        self.assertEqual(
            [event.action for event in events],
            [
                ProfileAuditEvent.Action.DEACTIVATED,
                ProfileAuditEvent.Action.REACTIVATED,
            ],
        )
        self.assertTrue(all(event.actor == self.admin for event in events))
        self.assertTrue(all(event.profile_id == profile.pk for event in events))

    def test_profile_status_endpoint_rejects_empty_payload(self):
        profile = HealthProfile.objects.get(user__email="alex@example.com")

        response = self.client.patch(
            self.status_url.format(profile.pk),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_active", response.data)
        profile.refresh_from_db()
        self.assertTrue(profile.is_active)
        self.assertFalse(ProfileAuditEvent.objects.exists())

    def test_profile_status_endpoint_requires_is_active(self):
        profile = HealthProfile.objects.get(user__email="alex@example.com")

        response = self.client.patch(
            self.status_url.format(profile.pk),
            {"unexpected": "value"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_active", response.data)
        profile.refresh_from_db()
        self.assertTrue(profile.is_active)
        self.assertFalse(ProfileAuditEvent.objects.exists())

    def test_profile_status_endpoint_rejects_non_boolean_values(self):
        profile = HealthProfile.objects.get(user__email="alex@example.com")

        for value in ("true", "false", "yes", 0, 1, None):
            with self.subTest(value=value):
                response = self.client.patch(
                    self.status_url.format(profile.pk),
                    {"is_active": value},
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                profile.refresh_from_db()
                self.assertTrue(profile.is_active)
                self.assertFalse(ProfileAuditEvent.objects.exists())

    def test_profile_status_endpoint_rejects_unexpected_fields(self):
        profile = HealthProfile.objects.get(user__email="alex@example.com")

        response = self.client.patch(
            self.status_url.format(profile.pk),
            {"is_active": False, "role": "admin"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        profile.refresh_from_db()
        self.assertTrue(profile.is_active)
        self.assertFalse(ProfileAuditEvent.objects.exists())

    def test_repeating_active_status_is_successful_without_audit_event(self):
        profile = HealthProfile.objects.get(user__email="alex@example.com")

        response = self.client.patch(
            self.status_url.format(profile.pk),
            {"is_active": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_active"])
        self.assertEqual(
            ProfileAuditEvent.objects.filter(profile_id=profile.pk).count(),
            0,
        )

    def test_repeating_inactive_status_is_successful_without_audit_event(self):
        profile = HealthProfile.objects.get(user__email="blair@example.com")

        response = self.client.patch(
            self.status_url.format(profile.pk),
            {"is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_active"])
        self.assertFalse(ProfileAuditEvent.objects.exists())

    def test_anonymous_and_standard_users_cannot_change_profile_status(self):
        profile = HealthProfile.objects.get(user__email="alex@example.com")
        self.client.logout()

        anonymous_response = self.client.patch(
            self.status_url.format(profile.pk),
            {"is_active": False},
            format="json",
        )
        standard_user = User.objects.get(email="alex@example.com")
        self.client.force_login(standard_user)
        standard_response = self.client.patch(
            self.status_url.format(profile.pk),
            {"is_active": False},
            format="json",
        )

        self.assertEqual(anonymous_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(standard_response.status_code, status.HTTP_403_FORBIDDEN)
        profile.refresh_from_db()
        self.assertTrue(profile.is_active)
        self.assertFalse(ProfileAuditEvent.objects.exists())

    def test_profile_status_mutation_requires_csrf(self):
        profile = HealthProfile.objects.get(user__email="alex@example.com")
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        csrf_response = csrf_client.get("/api/admin/csrf/")
        self.assertEqual(csrf_response.status_code, status.HTTP_200_OK)
        csrf_token = csrf_response.data["csrf_token"]

        missing_token_response = csrf_client.patch(
            self.status_url.format(profile.pk),
            {"is_active": False},
            format="json",
        )
        invalid_token_response = csrf_client.patch(
            self.status_url.format(profile.pk),
            {"is_active": False},
            format="json",
            HTTP_X_CSRFTOKEN="invalid-token",
        )
        valid_token_response = csrf_client.patch(
            self.status_url.format(profile.pk),
            {"is_active": False},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(missing_token_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(invalid_token_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(valid_token_response.status_code, status.HTTP_200_OK)
        event = ProfileAuditEvent.objects.get()
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.action, ProfileAuditEvent.Action.DEACTIVATED)
        self.assertEqual(event.profile_id, profile.pk)
