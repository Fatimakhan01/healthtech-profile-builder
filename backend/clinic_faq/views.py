import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsStandardUser

from .guardrails import appears_sensitive
from .provider import (
    FAQConfigurationError,
    FAQMalformedResponse,
    FAQProviderError,
    FAQProviderTimeout,
    answer_question,
)
from .serializers import FAQAnswerSerializer, FAQQuestionSerializer


logger = logging.getLogger(__name__)


class ClinicFAQView(APIView):
    permission_classes = [IsAuthenticated, IsStandardUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "clinic_faq"

    def post(self, request):
        question_serializer = FAQQuestionSerializer(data=request.data)
        if not question_serializer.is_valid():
            return Response(
                question_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        question = question_serializer.validated_data["question"]
        if appears_sensitive(question):
            return Response(
                {
                    "detail": (
                        "Please ask a general policy question without patient "
                        "or personal health information."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            answer = answer_question(question)
        except FAQConfigurationError:
            return self._service_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The FAQ assistant is not configured.",
            )
        except FAQProviderTimeout:
            return self._service_error(
                status.HTTP_504_GATEWAY_TIMEOUT,
                "The FAQ assistant timed out. Please try again.",
            )
        except FAQProviderError as error:
            logger.warning(
                "Clinic FAQ request failed: stage=provider_error "
                "exception_class=%s",
                type(error).__name__,
            )
            return self._service_error(
                status.HTTP_502_BAD_GATEWAY,
                "The FAQ assistant could not provide a valid response.",
            )
        except FAQMalformedResponse as error:
            if error.json_error_position is not None:
                if error.content_length is not None:
                    logger.warning(
                        "Clinic FAQ request failed: stage=malformed_response "
                        "category=%s json_error_position=%d "
                        "extracted_content_length=%d",
                        error.code,
                        error.json_error_position,
                        error.content_length,
                    )
                else:
                    logger.warning(
                        "Clinic FAQ request failed: stage=malformed_response "
                        "category=%s json_error_position=%d",
                        error.code,
                        error.json_error_position,
                    )
            else:
                logger.warning(
                    "Clinic FAQ request failed: stage=malformed_response "
                    "category=%s",
                    error.code,
                )
            return self._service_error(
                status.HTTP_502_BAD_GATEWAY,
                "The FAQ assistant could not provide a valid response.",
            )

        response_serializer = FAQAnswerSerializer(data=answer)
        if not response_serializer.is_valid():
            logger.warning(
                "Clinic FAQ request failed: stage=answer_validation "
                "exception_code=serializer_validation_failed",
            )
            return self._service_error(
                status.HTTP_502_BAD_GATEWAY,
                "The FAQ assistant could not provide a valid response.",
            )
        return Response(response_serializer.validated_data)

    @staticmethod
    def _service_error(http_status, detail):
        return Response({"detail": detail}, status=http_status)
