from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from .models import User


class AdminSessionAuthenticationTests(APITestCase):
    csrf_url = "/api/admin/csrf/"
    login_url = "/api/admin/login/"
    session_url = "/api/admin/session/"

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.standard_user = User.objects.create_user(
            email="standard@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf_token(self):
        response = self.client.get(self.csrf_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("csrftoken", self.client.cookies)
        return response.data["csrf_token"]

    def login(self, email, password):
        return self.client.post(
            self.login_url,
            {"email": email, "password": password},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

    def test_admin_login_creates_server_session(self):
        response = self.login(
            "ADMIN@EXAMPLE.COM",
            "A-strong-but-not-real-password-834!",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["email"], self.admin.email)
        self.assertNotIn("access_token", response.data)
        self.assertIn("sessionid", self.client.cookies)
        session_response = self.client.get(self.session_url)
        self.assertEqual(session_response.status_code, status.HTTP_200_OK)

    def test_admin_login_rejects_invalid_credentials(self):
        response = self.login("admin@example.com", "incorrect-password")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data["detail"],
            "Invalid administrator credentials.",
        )

    def test_standard_user_cannot_log_in_to_admin_session(self):
        response = self.login(
            self.standard_user.email,
            "A-strong-but-not-real-password-834!",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("sessionid", self.client.cookies)

    def test_admin_login_requires_csrf_token(self):
        response = self.client.post(
            self.login_url,
            {
                "email": self.admin.email,
                "password": "A-strong-but-not-real-password-834!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_is_denied_admin_session_endpoint(self):
        response = self.client.get(self.session_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_ordinary_session_user_is_denied_admin_session_endpoint(self):
        self.client.force_login(self.standard_user)

        response = self.client.get(self.session_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_logout_requires_csrf_and_ends_admin_session(self):
        self.assertEqual(
            self.login("admin@example.com", "A-strong-but-not-real-password-834!").status_code,
            status.HTTP_200_OK,
        )
        csrf_token = self.client.get(self.csrf_url).data["csrf_token"]

        blocked_response = self.client.post(self.session_url)
        logout_response = self.client.post(
            self.session_url,
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(blocked_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(logout_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            self.client.get(self.session_url).status_code,
            status.HTTP_403_FORBIDDEN,
        )
