from collections.abc import Mapping

from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from profiles.models import HealthProfile, ProfileAuditEvent

from .managers import normalize_email
from .models import User


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="health_profile.full_name")

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "role")
        read_only_fields = fields


class SignupSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            allowed_fields = set(self.fields)
            unexpected_fields = set(data) - allowed_fields
            if unexpected_fields:
                raise serializers.ValidationError(
                    {"detail": "Unexpected fields are not allowed."}
                )
        return super().to_internal_value(data)

    def validate_email(self, value):
        email = normalize_email(value)
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate_password(self, value):
        user = User(email=self.initial_data.get("email", ""))
        try:
            password_validation.validate_password(value, user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        return value

    def create(self, validated_data):
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=validated_data["email"],
                    password=validated_data["password"],
                )
                profile = HealthProfile.objects.create(
                    user=user,
                    full_name=validated_data["full_name"],
                )
                ProfileAuditEvent.objects.create(
                    actor=user,
                    action=ProfileAuditEvent.Action.CREATED,
                    profile_id=profile.pk,
                )
        except IntegrityError as error:
            if User.objects.filter(email__iexact=validated_data["email"]).exists():
                raise serializers.ValidationError(
                    {"email": "An account with this email already exists."}
                ) from error
            raise
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        email = normalize_email(attrs["email"])
        user = authenticate(
            request=self.context.get("request"),
            username=email,
            password=attrs["password"],
        )
        if user is None or user.role != User.Role.STANDARD:
            raise AuthenticationFailed("Invalid email or password.")

        attrs["user"] = user
        return attrs
