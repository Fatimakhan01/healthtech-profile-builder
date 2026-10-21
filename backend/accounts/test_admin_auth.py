from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone
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
        self.assertIn("csrf_token", response.data)
        self.assertNotIn("access_token", response.data)
        self.assertIn("sessionid", self.client.cookies)
        session_response = self.client.get(self.session_url)
        self.assertEqual(session_response.status_code, status.HTTP_200_OK)

    def test_admin_session_has_explicit_eight_hour_server_expiry(self):
        response = self.login(
            "ADMIN@EXAMPLE.COM",
            "A-strong-but-not-real-password-834!",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session_key = self.client.cookies["sessionid"].value
        session = Session.objects.get(session_key=session_key)
        expected_expiry = timezone.now() + timedelta(
            seconds=settings.ADMIN_SESSION_AGE
        )

        self.assertEqual(settings.ADMIN_SESSION_AGE, 8 * 60 * 60)
        self.assertEqual(settings.SESSION_COOKIE_AGE, 14 * 24 * 60 * 60)
        self.assertFalse(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertAlmostEqual(
            session.expire_date.timestamp(),
            expected_expiry.timestamp(),
            delta=5,
        )

    def test_expired_server_side_admin_session_is_denied(self):
        response = self.login(
            "ADMIN@EXAMPLE.COM",
            "A-strong-but-not-real-password-834!",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session_key = self.client.cookies["sessionid"].value
        Session.objects.filter(session_key=session_key).update(
            expire_date=timezone.now() - timedelta(seconds=1)
        )

        session_response = self.client.get(self.session_url)

        self.assertEqual(session_response.status_code, status.HTTP_403_FORBIDDEN)

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
        initial_csrf_token = self.csrf_token()
        login_response = self.client.post(
            self.login_url,
            {
                "email": "admin@example.com",
                "password": "A-strong-but-not-real-password-834!",
            },
            format="json",
            HTTP_X_CSRFTOKEN=initial_csrf_token,
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        csrf_token = login_response.data["csrf_token"]
        session_key = self.client.cookies["sessionid"].value

        blocked_response = self.client.post(self.session_url)
        stale_token_response = self.client.post(
            self.session_url,
            HTTP_X_CSRFTOKEN=initial_csrf_token,
        )
        logout_response = self.client.post(
            self.session_url,
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(blocked_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(stale_token_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(logout_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            Session.objects.filter(session_key=session_key).exists()
        )
        self.assertEqual(
            self.client.get(self.session_url).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.get("/api/admin/profiles/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_logout_rejects_invalid_csrf_token(self):
        self.assertEqual(
            self.login(
                "admin@example.com",
                "A-strong-but-not-real-password-834!",
            ).status_code,
            status.HTTP_200_OK,
        )

        response = self.client.post(
            self.session_url,
            HTTP_X_CSRFTOKEN="invalid-csrf-token",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.get(self.session_url).status_code,
            status.HTTP_200_OK,
        )
