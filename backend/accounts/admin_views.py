from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .admin_serializers import AdminLoginSerializer


class AdminCsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class AdminLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request=request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None or not user.is_active or not user.is_staff:
            return Response(
                {"detail": "Invalid administrator credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        return Response(
            {
                "user": {"id": user.pk, "email": user.email, "role": user.role},
                "csrf_token": get_token(request),
            }
        )


class AdminSessionView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(
            {
                "user": {
                    "id": request.user.pk,
                    "email": request.user.email,
                    "role": request.user.role,
                }
            }
        )

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
