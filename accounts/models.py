from __future__ import annotations

import uuid

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from .managers import UserManager


username_validator = RegexValidator(
    regex=r"^[A-Za-z0-9_.]+$",
    message="Username may contain only letters, numbers, underscores, and dots.",
)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        INSTRUCTOR = "instructor", "Instructor"
        ADMIN = "admin", "Admin"
        SUPPORT = "support", "Support"

    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "Pending verification"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DEACTIVATED = "deactivated", "Deactivated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        validators=[username_validator],
        help_text="Optional public handle. Email remains the primary login credential.",
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=24, choices=Role.choices, default=Role.STUDENT, db_index=True)
    avatar = models.URLField(max_length=500, blank=True)
    bio = models.TextField(blank=True)
    is_email_verified = models.BooleanField(default=False, db_index=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING_VERIFICATION,
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_staff = models.BooleanField(default=False, db_index=True)
    date_joined = models.DateTimeField(default=timezone.now, db_index=True)
    last_password_changed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ["-date_joined", "email"]

    def __str__(self) -> str:
        return self.email or str(self.pk)

    @property
    def full_name(self) -> str:
        return " ".join(part for part in [self.first_name, self.last_name] if part).strip()

    @property
    def display_name(self) -> str:
        return self.full_name or self.username or self.email

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.first_name or self.username or self.email

    def mark_email_verified(self) -> None:
        verified_at = timezone.now()
        self.is_email_verified = True
        self.email_verified_at = verified_at
        if self.status == self.Status.PENDING_VERIFICATION:
            self.status = self.Status.ACTIVE
        self.save(update_fields=["is_email_verified", "email_verified_at", "status", "updated_at"])

    def mark_password_changed(self) -> None:
        self.last_password_changed_at = timezone.now()
        self.save(update_fields=["last_password_changed_at", "updated_at"])

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        self.username = (self.username or "").strip() or None
        if self.is_email_verified and not self.email_verified_at:
            self.email_verified_at = timezone.now()
        if self.role == self.Role.ADMIN and not self.is_staff:
            self.is_staff = True
        super().save(*args, **kwargs)

