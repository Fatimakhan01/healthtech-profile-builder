from django.urls import path

from .views import CurrentHealthProfileView

app_name = "profiles"

urlpatterns = [
    path("me/", CurrentHealthProfileView.as_view(), name="current-profile"),
]
