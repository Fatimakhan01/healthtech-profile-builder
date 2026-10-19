from django.urls import path

from .admin_views import AdminCsrfView, AdminLoginView, AdminSessionView
from profiles.admin_views import AdminProfileListView, AdminProfileStatusView

app_name = "admin_auth"

urlpatterns = [
    path("csrf/", AdminCsrfView.as_view(), name="csrf"),
    path("login/", AdminLoginView.as_view(), name="login"),
    path("session/", AdminSessionView.as_view(), name="session"),
    path("profiles/", AdminProfileListView.as_view(), name="profiles"),
    path(
        "profiles/<int:profile_id>/status/",
        AdminProfileStatusView.as_view(),
        name="profile-status",
    ),
]
