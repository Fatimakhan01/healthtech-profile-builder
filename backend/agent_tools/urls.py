from django.urls import path

from .views import AgentView


app_name = "agent_tools"

urlpatterns = [
    path("ask/", AgentView.as_view(), name="ask"),
]
