from django.contrib import admin

from . import models


@admin.register(models.Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "category", "instructor_name", "price_value", "is_custom")
    list_filter = ("category", "level", "is_custom")
    search_fields = ("title", "slug", "instructor_name", "overview")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(models.Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "type", "value", "active")
    list_filter = ("type", "active")
    search_fields = ("code", "description")


@admin.register(models.NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "status", "subscribed_at")
    search_fields = ("email",)


@admin.register(models.ApiSession)
class ApiSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "token", "created_at", "expires_at", "revoked_at")
    search_fields = ("user__username", "user__email", "token")
    list_filter = ("revoked_at",)


@admin.register(models.PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "token", "created_at", "expires_at", "consumed_at")
    search_fields = ("user__username", "user__email", "token")


@admin.register(models.Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("course", "email", "status", "progress_percent", "created_at")
    search_fields = ("email", "course__title")
    list_filter = ("status",)


@admin.register(models.WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("course", "email", "created_at")
    search_fields = ("email", "course__title")


@admin.register(models.UserCourseNote)
class UserCourseNoteAdmin(admin.ModelAdmin):
    list_display = ("course", "email", "updated_at")
    search_fields = ("email", "course__title", "notes")


@admin.register(models.PlatformNotification)
class PlatformNotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "audience_scope", "audience_email", "created_at")
    list_filter = ("audience_scope",)
    search_fields = ("title", "message", "audience_email")


@admin.register(models.CourseShare)
class CourseShareAdmin(admin.ModelAdmin):
    list_display = ("course", "email", "url", "created_at")
    search_fields = ("email", "course__title", "url")


@admin.register(models.Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ("course", "email", "recipient_email", "status", "created_at")
    search_fields = ("email", "recipient_email", "course__title")
    list_filter = ("status",)


@admin.register(models.InstructorDraftRequest)
class InstructorDraftRequestAdmin(admin.ModelAdmin):
    list_display = ("instructor_name", "email", "status", "created_at")
    search_fields = ("instructor_name", "email")
    list_filter = ("status",)


@admin.register(models.DashboardSelection)
class DashboardSelectionAdmin(admin.ModelAdmin):
    list_display = ("tab", "email", "created_at")
    search_fields = ("tab", "email")


@admin.register(models.CertificateAction)
class CertificateActionAdmin(admin.ModelAdmin):
    list_display = ("action", "name", "email", "created_at")
    search_fields = ("action", "name", "email")


@admin.register(models.OAuthState)
class OAuthStateAdmin(admin.ModelAdmin):
    list_display = ("provider", "state", "created_at", "expires_at", "consumed_at")
    search_fields = ("provider", "state")


@admin.register(models.AIPromptLog)
class AIPromptLogAdmin(admin.ModelAdmin):
    list_display = ("email", "course", "created_at")
    search_fields = ("email", "prompt", "reply", "course__title")


@admin.register(models.AuthAuditLog)
class AuthAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "email", "created_at")
    search_fields = ("action", "email")
