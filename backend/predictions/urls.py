from django.urls import path

from .views import NoShowPredictionView


urlpatterns = [
    path("no-show/", NoShowPredictionView.as_view(), name="no-show-prediction"),
]
