from django.urls import path

from .views import MLDashboardDataView


urlpatterns = [
    path("", MLDashboardDataView.as_view(), name="ml-dashboard-data"),
]
