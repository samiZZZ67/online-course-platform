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


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        INSTRUCTOR = "instructor", "Instructor"
        ADMIN = "admin", "Admin"
        SUPPORT = "support", "Support"

    class TwoFactorMethod(models.TextChoices):
        EMAIL_OTP = "email_otp", "Email OTP"
        AUTHENTICATOR_APP = "authenticator_app", "Authenticator App"
        SMS_OTP = "sms_otp", "SMS OTP"

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
    social_links = models.JSONField(default=dict, blank=True)
    is_email_verified = models.BooleanField(default=False, db_index=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING_VERIFICATION,
        db_index=True,
    )
    two_factor_enabled = models.BooleanField(default=False, db_index=True)
    two_factor_method = models.CharField(
        max_length=32,
        choices=TwoFactorMethod.choices,
        default=TwoFactorMethod.EMAIL_OTP,
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

    def ensure_student_profile(self):
        return StudentProfile.objects.get_or_create(user=self)[0]

    def ensure_instructor_profile(self):
        return InstructorProfile.objects.get_or_create(user=self)[0]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        self.username = (self.username or "").strip() or None
        if self.is_email_verified and not self.email_verified_at:
            self.email_verified_at = timezone.now()
        if self.role == self.Role.ADMIN and not self.is_staff:
            self.is_staff = True
        if self.role in {self.Role.INSTRUCTOR, self.Role.ADMIN} and not self.two_factor_enabled:
            self.two_factor_enabled = True
        super().save(*args, **kwargs)


class StudentProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    learning_streak_days = models.PositiveIntegerField(default=0)
    completed_courses_count = models.PositiveIntegerField(default=0)
    current_courses_count = models.PositiveIntegerField(default=0)
    saved_courses_count = models.PositiveIntegerField(default=0)
    average_progress_percent = models.PositiveSmallIntegerField(default=0)
    total_learning_minutes = models.PositiveIntegerField(default=0)
    learning_statistics = models.JSONField(default=dict, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["user__email"]

    def __str__(self) -> str:
        return f"Student profile: {self.user.email}"


class InstructorProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="instructor_profile")
    expertise = models.JSONField(default=list, blank=True)
    biography = models.TextField(blank=True)
    revenue_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    published_courses_count = models.PositiveIntegerField(default=0)
    total_students_taught = models.PositiveIntegerField(default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    teaching_statistics = models.JSONField(default=dict, blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    is_verified_instructor = models.BooleanField(default=False, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["user__email"]

    def __str__(self) -> str:
        return f"Instructor profile: {self.user.email}"

    def mark_verified(self) -> None:
        self.is_verified_instructor = True
        self.verified_at = timezone.now()
        self.save(update_fields=["is_verified_instructor", "verified_at", "updated_at"])


class RefreshToken(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refresh_tokens")
    jti = models.CharField(max_length=64, unique=True, db_index=True)
    family_id = models.UUIDField(db_index=True)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    session_expires_at = models.DateTimeField(db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    reuse_detected_at = models.DateTimeField(null=True, blank=True)
    replaced_by = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replaces",
    )
    created_ip = models.CharField(max_length=64, blank=True)
    created_user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Refresh token for {self.user.email} ({self.jti[:12]})"


class EmailVerificationToken(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_verification_tokens")
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    sent_to_email = models.EmailField(blank=True)
    created_ip = models.CharField(max_length=64, blank=True)
    created_user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Email verification token for {self.user.email}"


class TwoFactorChallenge(TimeStampedModel):
    class Method(models.TextChoices):
        EMAIL_OTP = "email_otp", "Email OTP"
        AUTHENTICATOR_APP = "authenticator_app", "Authenticator App"
        SMS_OTP = "sms_otp", "SMS OTP"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="two_factor_challenges")
    method = models.CharField(max_length=32, choices=Method.choices, default=Method.EMAIL_OTP)
    code_hash = models.CharField(max_length=64, db_index=True)
    delivery_target = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    created_ip = models.CharField(max_length=64, blank=True)
    created_user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"2FA challenge for {self.user.email}"
