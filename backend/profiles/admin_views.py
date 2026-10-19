from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .admin_serializers import (
    AdminHealthProfileSerializer,
    AdminProfileStatusSerializer,
)
from .models import HealthProfile


class AdminProfilePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class AdminProfileListView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]
    serializer_class = AdminHealthProfileSerializer
    pagination_class = AdminProfilePagination

    def get_queryset(self):
        queryset = HealthProfile.objects.select_related("user")
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search) | Q(user__email__icontains=search)
            )

        active = self.request.query_params.get("active")
        if active is not None:
            normalized_active = active.lower()
            if normalized_active not in {"true", "false"}:
                raise ValidationError({"active": "Use 'true' or 'false'."})
            queryset = queryset.filter(is_active=normalized_active == "true")
        return queryset


class AdminProfileStatusView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    def patch(self, request, profile_id):
        profile = get_object_or_404(HealthProfile, pk=profile_id)
        serializer = AdminProfileStatusSerializer(
            profile,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            AdminHealthProfileSerializer(serializer.instance).data,
            status=status.HTTP_200_OK,
        )
