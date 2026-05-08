from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from .utils import DEFAULT_ACTOR_EMAIL


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserEmailMixin(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)ss",
    )
    email = models.EmailField(default=DEFAULT_ACTOR_EMAIL, db_index=True)

    class Meta:
        abstract = True


class Course(TimeStampedModel):
    slug = models.SlugField(max_length=140, unique=True)
    category = models.CharField(max_length=32, db_index=True)
    mark = models.CharField(max_length=8, default="CR")
    title = models.CharField(max_length=255)
    instructor_name = models.CharField(max_length=255)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    reviews_count = models.PositiveIntegerField(default=0)
    students_count = models.PositiveIntegerField(default=0)
    price_value = models.PositiveIntegerField(default=0)
    original_price_value = models.PositiveIntegerField(default=0)
    badge = models.CharField(max_length=64, blank=True)
    badge_class = models.CharField(max_length=64, blank=True)
    lessons_count = models.PositiveIntegerField(default=0)
    hours = models.PositiveIntegerField(default=0)
    level = models.CharField(max_length=64, default="Beginner")
    updated_label = models.CharField(max_length=64, blank=True)
    updated_sort = models.PositiveIntegerField(default=0, db_index=True)
    projects_count = models.PositiveIntegerField(default=0)
    gradient = models.CharField(max_length=255, blank=True)
    overview = models.TextField()
    thumbnail = models.TextField(blank=True)
    track = models.CharField(max_length=128, blank=True)
    requirements = models.JSONField(default=list, blank=True)
    learn = models.JSONField(default=list, blank=True)
    resources = models.JSONField(default=list, blank=True)
    qa = models.JSONField(default=list, blank=True)
    modules = models.JSONField(default=list, blank=True)
    is_custom = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="academy_created_courses",
    )

    class Meta:
        ordering = ["-updated_sort", "title"]

    def __str__(self) -> str:
        return self.title


class Coupon(TimeStampedModel):
    TYPE_PERCENT = "percent"
    TYPE_FIXED = "fixed"
    TYPE_CHOICES = [
        (TYPE_PERCENT, "Percent"),
        (TYPE_FIXED, "Fixed"),
    ]

    code = models.CharField(max_length=64, unique=True)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    value = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class NewsletterSubscriber(TimeStampedModel):
    email = models.EmailField(unique=True)
    status = models.CharField(max_length=32, default="subscribed")
    subscribed_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return self.email


class AuthAuditLog(TimeStampedModel):
    ACTION_CHOICES = [
        ("signup", "Signup"),
        ("login", "Login"),
        ("logout", "Logout"),
        ("password_reset.request", "Password Reset Request"),
        ("password_reset.confirm", "Password Reset Confirm"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="auth_audit_logs",
    )
    email = models.EmailField(default=DEFAULT_ACTOR_EMAIL, db_index=True)
    action = models.CharField(max_length=64, choices=ACTION_CHOICES)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} - {self.email}"


class ApiSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_sessions")
    token = models.CharField(max_length=96, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_seen_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    ip_address = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} ({self.token[:14]})"


class OAuthState(models.Model):
    provider = models.CharField(max_length=32)
    state = models.CharField(max_length=96, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class PasswordResetToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_tokens")
    token = models.CharField(max_length=96, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class Enrollment(UserEmailMixin):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(max_length=32, default="active")
    progress_percent = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["email", "course"], name="unique_enrollment_email_course"),
        ]
        ordering = ["-created_at"]


class WishlistItem(UserEmailMixin):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="wishlist_items")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["email", "course"], name="unique_wishlist_email_course"),
        ]
        ordering = ["-created_at"]


class UserCourseNote(UserEmailMixin):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="notes")
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["email", "course"], name="unique_note_email_course"),
        ]


class AIPromptLog(UserEmailMixin):
    course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.SET_NULL, related_name="ai_prompts")
    lesson_id = models.CharField(max_length=128, blank=True)
    prompt = models.TextField()
    reply = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class CourseShare(UserEmailMixin):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="shares")
    url = models.URLField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Gift(UserEmailMixin):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="gifts")
    recipient_email = models.EmailField()
    status = models.CharField(max_length=32, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PlatformNotification(TimeStampedModel):
    SCOPE_ALL = "all"
    SCOPE_EMAIL = "email"
    SCOPE_USER = "user"
    SCOPE_CHOICES = [
        (SCOPE_ALL, "All"),
        (SCOPE_EMAIL, "Email"),
        (SCOPE_USER, "User"),
    ]

    audience_scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, default=SCOPE_ALL)
    audience_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="platform_notifications",
    )
    audience_email = models.EmailField(blank=True)
    title = models.CharField(max_length=255)
    message = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class InstructorDraftRequest(UserEmailMixin):
    instructor_name = models.CharField(max_length=255)
    status = models.CharField(max_length=32, default="open")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class DashboardSelection(UserEmailMixin):
    tab = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class CertificateAction(UserEmailMixin):
    action = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
