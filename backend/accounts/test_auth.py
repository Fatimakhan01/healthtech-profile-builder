from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from profiles.models import HealthProfile

from .models import User


class StandardUserAuthenticationTests(APITestCase):
    signup_url = "/api/auth/signup/"
    login_url = "/api/auth/login/"
    current_user_url = "/api/auth/me/"

    def signup_payload(self, **overrides):
        payload = {
            "full_name": "Example Person",
            "email": "person@example.com",
            "password": "A-strong-but-not-real-password-834!",
        }
        payload.update(overrides)
        return payload

    def create_standard_user(self, email="person@example.com", password=None):
        user = User.objects.create_user(
            email=email,
            password=password or "A-strong-but-not-real-password-834!",
        )
        HealthProfile.objects.create(user=user, full_name="Example Person")
        return user

    def test_signup_creates_standard_user_and_profile_without_returning_password(self):
        response = self.client.post(
            self.signup_url,
            self.signup_payload(email=" Person@Example.COM "),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="person@example.com")
        self.assertEqual(user.role, User.Role.STANDARD)
        self.assertTrue(user.check_password("A-strong-but-not-real-password-834!"))
        self.assertNotEqual(user.password, "A-strong-but-not-real-password-834!")
        self.assertEqual(user.health_profile.full_name, "Example Person")
        self.assertEqual(response.data["user"]["email"], "person@example.com")
        self.assertNotIn("password", response.data["user"])
        self.assertNotIn("password", response.data)

    def test_login_returns_short_lived_access_token_for_standard_user(self):
        self.create_standard_user()

        response = self.client.post(
            self.login_url,
            {
                "email": "PERSON@EXAMPLE.COM",
                "password": "A-strong-but-not-real-password-834!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token_type"], "Bearer")
        self.assertEqual(response.data["expires_in"], 300)
        self.assertIn("access_token", response.data)
        self.assertNotIn("refresh_token", response.data)
        self.assertNotIn("password", response.data["user"])

    def test_invalid_credentials_return_safe_error(self):
        self.create_standard_user()

        response = self.client.post(
            self.login_url,
            {"email": "person@example.com", "password": "incorrect-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["detail"], "Invalid email or password.")

    def test_administrator_cannot_use_standard_user_login(self):
        User.objects.create_superuser(
            email="admin@example.com",
            password="A-strong-but-not-real-password-834!",
        )

        response = self.client.post(
            self.login_url,
            {
                "email": "admin@example.com",
                "password": "A-strong-but-not-real-password-834!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["detail"], "Invalid email or password.")

    def test_signup_rejects_duplicate_email_with_different_casing(self):
        self.create_standard_user()

        response = self.client.post(
            self.signup_url,
            self.signup_payload(email="PERSON@EXAMPLE.COM"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_signup_rejects_invalid_email(self):
        response = self.client.post(
            self.signup_url,
            self.signup_payload(email="not-an-email"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_signup_rejects_weak_password(self):
        response = self.client.post(
            self.signup_url,
            self.signup_payload(password="password"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_signup_rejects_admin_or_privilege_assignment(self):
        response = self.client.post(
            self.signup_url,
            self.signup_payload(
                role=User.Role.ADMIN,
                is_staff=True,
                is_superuser=True,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)

    def test_current_user_requires_access_token(self):
        response = self.client.get(self.current_user_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_current_user_rejects_malformed_token(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-valid-token")

        response = self.client.get(self.current_user_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_current_user_rejects_expired_token(self):
        user = self.create_standard_user()
        token = AccessToken.for_user(user)
        token.set_exp(from_time=timezone.now() - timedelta(minutes=10))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get(self.current_user_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_current_user_rejects_inactive_user(self):
        user = self.create_standard_user()
        token = AccessToken.for_user(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get(self.current_user_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_current_user_returns_safe_standard_user_fields(self):
        user = self.create_standard_user()
        token = AccessToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get(self.current_user_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["email"], user.email)
        self.assertEqual(response.data["user"]["full_name"], "Example Person")
        self.assertNotIn("password", response.data["user"])
