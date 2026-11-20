from django.db.models import QuerySet
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import WorkflowJob
from .serializers import EnqueueWorkflowJobSerializer, WorkflowJobSerializer
from .services import (
    IdempotencyConflict,
    enqueue_job,
    monitoring_summary,
)


class WorkflowJobPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class WorkflowAuditView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]
    pagination_class = WorkflowJobPagination

    def get(self, request):
        queryset: QuerySet = WorkflowJob.objects.order_by("-created_at")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serialized = WorkflowJobSerializer(page, many=True).data
        response_data = paginator.get_paginated_response(serialized).data
        response_data["monitoring"] = monitoring_summary()
        return Response(
            response_data,
            headers={"Cache-Control": "no-store"},
        )


class EnqueueWorkflowJobView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = EnqueueWorkflowJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = request.headers.get("Idempotency-Key", "")
        try:
            job, created = enqueue_job(
                serializer.validated_data["job_type"],
                idempotency_key,
                actor=request.user,
            )
        except IdempotencyConflict as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_409_CONFLICT,
                headers={"Cache-Control": "no-store"},
            )
        except ValueError as error:
            raise ValidationError({"Idempotency-Key": str(error)}) from error

        return Response(
            {
                "job": WorkflowJobSerializer(job).data,
                "created": created,
            },
            status=(
                status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
            ),
            headers={"Cache-Control": "no-store"},
        )
