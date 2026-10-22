from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsStandardUser

from .models import HealthProfile
from .serializers import HealthProfileSerializer


class CurrentHealthProfileView(generics.RetrieveUpdateDestroyAPIView):
    """Manage the current user's profile at /api/profiles/me/.

    DELETE removes only the profile and returns 204; absent profiles return 404.
    POST recreates a missing profile from serializer fields and returns 201;
    it returns 409 if a profile already exists.
    """

    serializer_class = HealthProfileSerializer
    permission_classes = [IsAuthenticated, IsStandardUser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_object(self):
        return get_object_or_404(HealthProfile, user=self.request.user)

    def post(self, request):
        if HealthProfile.objects.filter(user=request.user).exists():
            return Response(
                {"detail": "A health profile already exists."},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                profile = serializer.save(user=request.user)
        except IntegrityError:
            if HealthProfile.objects.filter(user=request.user).exists():
                return Response(
                    {"detail": "A health profile already exists."},
                    status=status.HTTP_409_CONFLICT,
                )
            raise

        return Response(
            self.get_serializer(profile).data,
            status=status.HTTP_201_CREATED,
        )
