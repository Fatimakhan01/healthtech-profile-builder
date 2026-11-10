from collections.abc import Mapping

from rest_framework import serializers


class FAQQuestionSerializer(serializers.Serializer):
    question = serializers.CharField(
        max_length=1_000,
        allow_blank=False,
        trim_whitespace=True,
    )

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unexpected = set(data) - {"question"}
            if unexpected:
                raise serializers.ValidationError(
                    {"detail": "Only the question field is accepted."}
                )
            if "question" in data and not isinstance(data["question"], str):
                raise serializers.ValidationError(
                    {"question": ["A valid string is required."]}
                )
        return super().to_internal_value(data)


class FAQCitationSerializer(serializers.Serializer):
    title = serializers.CharField()
    filename = serializers.CharField()


class FAQAnswerSerializer(serializers.Serializer):
    answer = serializers.CharField()
    insufficient_information = serializers.BooleanField()
    citations = FAQCitationSerializer(many=True)
