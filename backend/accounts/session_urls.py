from django.urls import path

from .session_views import (
    StandardUserCsrfView,
    StandardUserSessionLoginView,
    StandardUserSessionLogoutView,
    StandardUserSessionRefreshView,
)

app_name = "standard_user_session"

urlpatterns = [
    path("csrf/", StandardUserCsrfView.as_view(), name="csrf"),
    path("session/login/", StandardUserSessionLoginView.as_view(), name="login"),
    path("session/refresh/", StandardUserSessionRefreshView.as_view(), name="refresh"),
    path("session/logout/", StandardUserSessionLogoutView.as_view(), name="logout"),
]
