from django.urls import path

from .views import ClinicFAQView


app_name = "clinic_faq"

urlpatterns = [
    path("ask/", ClinicFAQView.as_view(), name="ask"),
]
