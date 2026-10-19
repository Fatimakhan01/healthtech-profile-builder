from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import HealthProfile


class AdminProfileListApiTests(APITestCase):
    profiles_url = "/api/admin/profiles/"

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
