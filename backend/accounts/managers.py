from django.contrib.auth.base_user import BaseUserManager


def normalize_email(email):
    return email.strip().lower()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email or not email.strip():
            raise ValueError("An email address is required.")
        if not password:
            raise ValueError("A password is required.")

        user = self.model(email=normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def get_by_natural_key(self, username):
        return self.get(email=normalize_email(username))

    def create_user(self, email, password=None, **extra_fields):
        if "role" in extra_fields or extra_fields.get("is_superuser"):
            raise ValueError("Use create_superuser to create an administrator.")

        extra_fields["role"] = self.model.Role.STANDARD
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", self.model.Role.ADMIN)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields["role"] != self.model.Role.ADMIN:
            raise ValueError("A superuser must have the administrator role.")
        if not extra_fields["is_superuser"]:
            raise ValueError("A superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)
