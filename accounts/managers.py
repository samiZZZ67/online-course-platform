from __future__ import annotations

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _normalize_email(self, email: str) -> str:
        return self.normalize_email(email).strip().lower()

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self._normalize_email(email)
        role = extra_fields.setdefault("role", "student")
        extra_fields.setdefault("status", "pending_verification")
        extra_fields.setdefault("two_factor_enabled", role in {"instructor", "admin"})
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        extra_fields.setdefault("status", "active")
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_email_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        user = self.create_user(email, password, **extra_fields)
        if not user.email_verified_at:
            from django.utils import timezone

            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
        return user
