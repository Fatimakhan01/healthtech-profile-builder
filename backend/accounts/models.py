from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from .managers import UserManager, normalize_email


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STANDARD = "standard", _("Standard user")
        ADMIN = "admin", _("Administrator")

    email = models.EmailField(max_length=254, unique=True)
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STANDARD,
    )
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="accounts_user_email_ci_unique",
            ),
        ]

    def clean(self):
        super().clean()
        self.email = normalize_email(self.email)

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)

    @property
    def is_staff(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    def __str__(self):
        return self.email
