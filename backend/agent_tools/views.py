from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsStandardUser

from .agent import (
    AgentAuthorizationError,
    AgentError,
    AgentMaxStepsExceeded,
    AgentPlannerError,
    AgentProviderError,
    AgentProviderTimeout,
    run_agent,
)
from .serializers import AgentRequestSerializer, AgentResponseSerializer


class AgentView(APIView):
    permission_classes = [IsAuthenticated, IsStandardUser]

    def post(self, request):
        request_serializer = AgentRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        try:
            result = run_agent(
                request_serializer.validated_data["message"],
                user=request.user,
                history=request_serializer.validated_data.get("history", []),
            )
        except AgentProviderTimeout:
            return Response(
                {"detail": "The local assistant timed out."},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except AgentAuthorizationError:
            return Response(
                {"detail": "A standard-user account is required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        except AgentProviderError:
            return Response(
                {"detail": "The local assistant is currently unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except AgentPlannerError:
            return Response(
                {"detail": "The local assistant returned an invalid plan."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except AgentMaxStepsExceeded:
            return Response(
                {"detail": "The request exceeded the tool execution limit."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except AgentError:
            return Response(
                {"detail": "The assistant request could not be completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = AgentResponseSerializer(data=result)
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
