from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import EmailVerificationToken, InstructorProfile, RefreshToken, StudentProfile, TwoFactorChallenge, User


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    extra = 0
    can_delete = False


class InstructorProfileInline(admin.StackedInline):
    model = InstructorProfile
    extra = 0
    can_delete = False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User
    ordering = ("email",)
    list_display = (
        "email",
        "username",
        "role",
        "status",
        "is_email_verified",
        "is_staff",
        "is_active",
        "date_joined",
        "last_login",
    )
    list_filter = ("role", "status", "is_email_verified", "is_staff", "is_active", "is_superuser")
    search_fields = ("email", "username", "first_name", "last_name")
    inlines = (StudentProfileInline, InstructorProfileInline)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("username", "first_name", "last_name", "avatar", "bio", "social_links")}),
        ("Access", {"fields": ("role", "status", "is_email_verified", "email_verified_at", "two_factor_enabled", "two_factor_method")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Security", {"fields": ("last_login", "last_password_changed_at")}),
        ("Dates", {"fields": ("date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "first_name", "last_name", "role", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("date_joined", "created_at", "updated_at", "last_login", "email_verified_at", "last_password_changed_at")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "learning_streak_days",
        "completed_courses_count",
        "current_courses_count",
        "saved_courses_count",
        "average_progress_percent",
        "updated_at",
    )
    search_fields = ("user__email", "user__username", "user__first_name", "user__last_name")


@admin.register(InstructorProfile)
class InstructorProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "published_courses_count",
        "total_students_taught",
        "average_rating",
        "revenue_total",
        "is_verified_instructor",
        "updated_at",
    )
    list_filter = ("is_verified_instructor",)
    search_fields = ("user__email", "user__username", "user__first_name", "user__last_name", "biography")


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "jti",
        "family_id",
        "expires_at",
        "session_expires_at",
        "last_used_at",
        "rotated_at",
        "revoked_at",
        "reuse_detected_at",
    )
    list_filter = ("revoked_at", "reuse_detected_at")
    search_fields = ("user__email", "user__username", "jti", "token_hash")


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "sent_to_email", "expires_at", "consumed_at", "created_at")
    list_filter = ("consumed_at",)
    search_fields = ("user__email", "user__username", "token_hash", "sent_to_email")


@admin.register(TwoFactorChallenge)
class TwoFactorChallengeAdmin(admin.ModelAdmin):
    list_display = ("user", "method", "delivery_target", "expires_at", "consumed_at", "attempts", "created_at")
    list_filter = ("method", "consumed_at")
    search_fields = ("user__email", "user__username", "delivery_target")
