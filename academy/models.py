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


class CourseCategory(TimeStampedModel):
    slug = models.SlugField(max_length=32, unique=True)
    code = models.CharField(max_length=8, unique=True)
    label = models.CharField(max_length=128)
    badge_class = models.CharField(max_length=64, blank=True)
    gradient = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    requirements = models.JSONField(default=list, blank=True)
    learn = models.JSONField(default=list, blank=True)
    resources = models.JSONField(default=list, blank=True)
    qa = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["sort_order", "label"]

    def __str__(self) -> str:
        return self.label


class Course(TimeStampedModel):
    slug = models.SlugField(max_length=140, unique=True)
    category = models.CharField(max_length=32, db_index=True)
    category_ref = models.ForeignKey(
        CourseCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="courses",
    )
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
        permissions = [
            ("manage_course_students", "Can manage enrolled students for owned courses"),
            ("view_course_analytics", "Can view instructor course analytics"),
            ("moderate_courses", "Can moderate and review course catalog content"),
            ("configure_platform", "Can configure platform settings"),
        ]

    def __str__(self) -> str:
        return self.title


class CourseModule(TimeStampedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="course_modules")
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    duration_label = models.CharField(max_length=32, blank=True)
    position = models.PositiveIntegerField(default=1, db_index=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["course", "position"], name="unique_course_module_position"),
        ]

    def __str__(self) -> str:
        return f"{self.course.title}: {self.title}"


class CourseLesson(TimeStampedModel):
    TYPE_VIDEO = "video"
    TYPE_QUIZ = "quiz"
    TYPE_PDF = "pdf"
    TYPE_ASSIGNMENT = "assignment"
    TYPE_CHOICES = [
        (TYPE_VIDEO, "Video"),
        (TYPE_QUIZ, "Quiz"),
        (TYPE_PDF, "PDF"),
        (TYPE_ASSIGNMENT, "Assignment"),
    ]

    module = models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name="lessons")
    lesson_key = models.SlugField(max_length=180, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    duration_label = models.CharField(max_length=32, blank=True)
    content_type = models.CharField(max_length=24, choices=TYPE_CHOICES, default=TYPE_VIDEO)
    position = models.PositiveIntegerField(default=1, db_index=True)
    is_free_preview = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    asset_url = models.URLField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["module__position", "position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["module", "position"], name="unique_course_lesson_position"),
        ]

    def __str__(self) -> str:
        return f"{self.module.course.title}: {self.title}"


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
        ("login_failed", "Login Failed"),
        ("two_factor.challenge", "Two-Factor Challenge"),
        ("two_factor.verify", "Two-Factor Verify"),
        ("two_factor.failed", "Two-Factor Failed"),
        ("refresh", "Refresh"),
        ("refresh.reuse_detected", "Refresh Reuse Detected"),
        ("logout", "Logout"),
        ("verify_email.request", "Verify Email Request"),
        ("verify_email.confirm", "Verify Email Confirm"),
        ("password_change", "Password Change"),
        ("password_reset.request", "Password Reset Request"),
        ("password_reset.confirm", "Password Reset Confirm"),
        ("admin.user_suspend", "Admin User Suspend"),
        ("admin.user_verify", "Admin User Verify"),
        ("admin.user_change_role", "Admin User Change Role"),
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
    current_lesson = models.ForeignKey(
        CourseLesson,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="current_enrollments",
    )
    status = models.CharField(max_length=32, default="active")
    progress_percent = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["email", "course"], name="unique_enrollment_email_course"),
        ]
        ordering = ["-created_at"]


class LessonProgress(UserEmailMixin):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="lesson_progress_items")
    lesson = models.ForeignKey(CourseLesson, on_delete=models.CASCADE, related_name="lesson_progress_items")
    status = models.CharField(max_length=32, default="not_started")
    progress_percent = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_position_seconds = models.PositiveIntegerField(default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["lesson__module__position", "lesson__position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "lesson"], name="unique_enrollment_lesson_progress"),
        ]


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
