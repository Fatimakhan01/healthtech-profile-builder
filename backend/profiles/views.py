from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from accounts.permissions import IsStandardUser

from .models import HealthProfile
from .serializers import HealthProfileSerializer


class CurrentHealthProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = HealthProfileSerializer
    permission_classes = [IsAuthenticated, IsStandardUser]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return get_object_or_404(HealthProfile, user=self.request.user)
