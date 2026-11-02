from collections.abc import Mapping

from rest_framework import serializers


class StrictIntegerField(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail("invalid")
        return super().to_internal_value(data)


class NoShowPredictionSerializer(serializers.Serializer):
    WEEKDAYS = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )

    days_ahead = StrictIntegerField(min_value=0, max_value=60)
    previous_no_shows = StrictIntegerField(min_value=0, max_value=5)
    sms_reminder = serializers.ChoiceField(choices=("yes", "no"))
    weekday = serializers.ChoiceField(choices=WEEKDAYS)

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown_fields = set(data) - set(self.fields)
            if unknown_fields:
                raise serializers.ValidationError(
                    {
                        field: ["Unknown field."]
                        for field in sorted(unknown_fields)
                    }
                )
        return super().to_internal_value(data)
