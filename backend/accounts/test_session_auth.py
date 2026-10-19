from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import User


class StandardUserSessionTests(APITestCase):
    csrf_url = "/api/auth/csrf/"
    login_url = "/api/auth/session/login/"
    refresh_url = "/api/auth/session/refresh/"
    logout_url = "/api/auth/session/logout/"

    def setUp(self):
        self.user = User.objects.create_user(
            email="standard@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf_token(self):
        response = self.client.get(self.csrf_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("csrftoken", self.client.cookies)
        return response.data["csrf_token"]

    def login(self):
        return self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": "A-strong-but-not-real-password-834!",
            },
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

    def test_login_issues_access_token_and_httponly_session_cookie(self):
        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.data)
        self.assertEqual(response.data["expires_in"], 300)
        self.assertNotIn("refresh_token", response.data)
        self.assertEqual(response.data["user"]["email"], self.user.email)
        self.assertIn("sessionid", self.client.cookies)
        self.assertTrue(self.client.cookies["sessionid"]["httponly"])

    def test_login_requires_csrf_token(self):
        response = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": "A-strong-but-not-real-password-834!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_refresh_issues_new_access_token_after_login(self):
        login_response = self.login()
        csrf_token = login_response.data["csrf_token"]

        response = self.client.post(
            self.refresh_url,
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.data)
        self.assertEqual(response.data["expires_in"], 300)
        self.assertEqual(response.data["user"]["email"], self.user.email)

    def test_refresh_requires_csrf_token(self):
        self.login()

        response = self.client.post(self.refresh_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_refresh_is_rejected(self):
        response = self.client.post(
            self.refresh_url,
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_session_cannot_refresh_standard_user_access_token(self):
        admin = User.objects.create_superuser(
            email="admin@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.client.force_login(admin)
        csrf_token = self.csrf_token()

        response = self.client.post(
            self.refresh_url,
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_invalidates_server_session(self):
        login_response = self.login()

        response = self.client.post(
            self.logout_url,
            HTTP_X_CSRFTOKEN=login_response.data["csrf_token"],
        )
        refresh_response = self.client.post(
            self.refresh_url,
            HTTP_X_CSRFTOKEN=login_response.data["csrf_token"],
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)
