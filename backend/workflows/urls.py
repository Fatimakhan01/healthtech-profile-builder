from django.urls import path

from .views import EnqueueWorkflowJobView, WorkflowAuditView


app_name = "workflows"

urlpatterns = [
    path("jobs/", WorkflowAuditView.as_view(), name="jobs"),
    path("enqueue/", EnqueueWorkflowJobView.as_view(), name="enqueue"),
]
