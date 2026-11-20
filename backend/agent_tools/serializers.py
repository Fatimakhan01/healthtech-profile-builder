from rest_framework import serializers

from clinic_faq.guardrails import appears_sensitive


MAX_HISTORY_TURNS = 8
MAX_HISTORY_CONTENT_LENGTH = 1000
MAX_HISTORY_TOTAL_LENGTH = 6000


class ConversationTurnSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=("user", "assistant"))
    content = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
        max_length=MAX_HISTORY_CONTENT_LENGTH,
    )

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != {"role", "content"}:
            raise serializers.ValidationError(
                "Each history item must contain only role and content."
            )
        return super().to_internal_value(data)


class AgentRequestSerializer(serializers.Serializer):
    message = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
        max_length=1000,
    )
    history = ConversationTurnSerializer(
        many=True,
        required=False,
        allow_empty=True,
        max_length=MAX_HISTORY_TURNS,
    )

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - {"message", "history"}:
            raise serializers.ValidationError("Unsupported request fields.")
        return super().to_internal_value(data)

    def validate(self, attrs):
        history = attrs.get("history", [])
        if sum(len(turn["content"]) for turn in history) > MAX_HISTORY_TOTAL_LENGTH:
            raise serializers.ValidationError(
                {"history": "Conversation history exceeds the supported size."}
            )
        if appears_sensitive(attrs["message"]) or any(
            appears_sensitive(turn["content"]) for turn in history
        ):
            raise serializers.ValidationError(
                {"message": "Sensitive personal information cannot be submitted."}
            )
        return attrs


class AgentResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    execution_trace = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField(),
        )
    )
