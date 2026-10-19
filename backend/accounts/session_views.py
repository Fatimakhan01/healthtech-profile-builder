from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken

from .managers import normalize_email
from .models import User
from .serializers import LoginSerializer, UserSerializer


class StandardUserCsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class StandardUserSessionLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request, user)
        return session_payload(request, user, start_session=True)


@method_decorator(csrf_protect, name="dispatch")
class StandardUserSessionRefreshView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        user = request.user
        if (
            not user.is_authenticated
            or not user.is_active
            or user.role != User.Role.STANDARD
        ):
            return Response(
                {"detail": "A valid standard-user session is required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return session_payload(request, user)


@method_decorator(csrf_protect, name="dispatch")
class StandardUserSessionLogoutView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        user = request.user
        if user.is_authenticated and user.role != User.Role.STANDARD:
            return Response(
                {"detail": "This endpoint is only for standard-user sessions."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if user.is_authenticated:
            logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


def session_payload(request, user, start_session=False):
    if start_session:
        request.session.set_expiry(None)
    return Response(
        {
            "access_token": str(AccessToken.for_user(user)),
            "token_type": "Bearer",
            "expires_in": int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
            "csrf_token": get_token(request),
            "user": UserSerializer(user).data,
        }
    )
