from pathlib import Path

from django import forms
from django.contrib import admin
from django.core.files.storage import default_storage
from django.db import models as django_models
from django.utils.html import format_html

from . import models
from .services import refresh_course_structure_snapshot
from .utils import build_token


VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".ogg"}
DOCUMENT_EXTENSIONS = {".pdf"}


def course_for_lesson(lesson: models.CourseLesson) -> models.Course | None:
    module = getattr(lesson, "module", None)
    return getattr(module, "course", None) if module else None


def store_lesson_media_file(lesson: models.CourseLesson, upload) -> str:
    course = course_for_lesson(lesson)
    course_slug = getattr(course, "slug", "") or "prototype-course"
    extension = Path(upload.name or "").suffix.lower()
    relative_path = default_storage.save(f"course-assets/{course_slug}/{build_token('lesson')}{extension}", upload)
    if extension in DOCUMENT_EXTENSIONS:
        lesson.content_type = models.CourseLesson.TYPE_PDF
    elif extension in VIDEO_EXTENSIONS:
        lesson.content_type = models.CourseLesson.TYPE_VIDEO
    return default_storage.url(relative_path)


class CourseLessonAdminForm(forms.ModelForm):
    asset_url = forms.CharField(
        required=False,
        help_text="Paste a hosted media URL or upload a prototype video/PDF below.",
    )
    media_file = forms.FileField(
        required=False,
        help_text="Upload a prototype lesson video or PDF. The player will use it immediately after save.",
    )
    lesson_key = forms.SlugField(
        required=False,
        help_text="Leave blank to generate one from the course, module, and lesson title.",
    )
    summary = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Short lesson content summary, including what should be covered in this hour or segment.",
    )

    class Meta:
        model = models.CourseLesson
        fields = "__all__"

    def save(self, commit=True):
        lesson = super().save(commit=False)
        upload = self.cleaned_data.get("media_file")
        if upload:
            lesson.asset_url = store_lesson_media_file(lesson, upload)
        if commit:
            lesson.save()
            self.save_m2m()
        return lesson


def refresh_admin_course_snapshot(course: models.Course | None) -> None:
    if course and getattr(course, "pk", None):
        refresh_course_structure_snapshot(course)


class CourseLessonInline(admin.StackedInline):
    model = models.CourseLesson
    form = CourseLessonAdminForm
    extra = 1
    fields = (
        "position",
        "lesson_key",
        "title",
        "summary",
        "content_type",
        "duration_label",
        "asset_url",
        "media_file",
        "is_free_preview",
        "is_published",
    )
    show_change_link = True
    verbose_name = "lesson or hourly content item"
    verbose_name_plural = "lessons and hourly content items"


class CourseModuleInline(admin.StackedInline):
    model = models.CourseModule
    extra = 1
    fields = ("position", "title", "summary", "duration_label", "is_published")
    show_change_link = True
    verbose_name = "course hour/module"
    verbose_name_plural = "course hours/modules"
    formfield_overrides = {
        django_models.TextField: {"widget": forms.Textarea(attrs={"rows": 3})},
    }


@admin.register(models.CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ("label", "slug", "code", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("label", "slug", "code", "description")


@admin.register(models.Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "category", "category_ref", "instructor_name", "hours", "lessons_count", "price_value", "is_custom")
    list_filter = ("category", "category_ref", "level", "is_custom")
    search_fields = ("title", "slug", "instructor_name", "overview")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("lessons_count", "frontend_links")
    fieldsets = (
        (
            "Course identity",
            {
                "fields": (
                    "title",
                    "slug",
                    "frontend_links",
                    "category",
                    "category_ref",
                    "mark",
                    "track",
                    "instructor_name",
                    "level",
                )
            },
        ),
        (
            "Course content summary",
            {
                "fields": (
                    "overview",
                    "requirements",
                    "learn",
                    "resources",
                    "qa",
                    "includes",
                )
            },
        ),
        (
            "Pricing and workload",
            {
                "fields": (
                    "price_value",
                    "original_price_value",
                    "hours",
                    "projects_count",
                    "lessons_count",
                    "rating",
                    "reviews_count",
                    "students_count",
                )
            },
        ),
        (
            "Catalog display",
            {
                "fields": (
                    "badge",
                    "badge_class",
                    "updated_label",
                    "updated_sort",
                    "gradient",
                    "thumbnail",
                    "is_custom",
                    "created_by",
                )
            },
        ),
    )
    formfield_overrides = {
        django_models.TextField: {"widget": forms.Textarea(attrs={"rows": 4})},
    }
    inlines = (CourseModuleInline,)

    @admin.display(description="Frontend links")
    def frontend_links(self, obj):
        if not obj or not getattr(obj, "slug", ""):
            return "Save the course to enable links."
        return format_html(
            '<a href="/#detail/{}" target="_blank">Course page</a> &nbsp; '
            '<a href="/#player/{}" target="_blank">Player</a> &nbsp; '
            '<a href="/#instructor" target="_blank">Instructor page</a>',
            obj.slug,
            obj.slug,
        )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        refresh_admin_course_snapshot(form.instance)


@admin.register(models.CourseModule)
class CourseModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "position", "duration_label", "is_published")
    list_filter = ("is_published", "course__category")
    search_fields = ("title", "summary", "course__title")
    fieldsets = (
        (
            "Hour/module content",
            {
                "fields": (
                    "course",
                    "position",
                    "title",
                    "summary",
                    "duration_label",
                    "is_published",
                )
            },
        ),
    )
    formfield_overrides = {
        django_models.TextField: {"widget": forms.Textarea(attrs={"rows": 4})},
    }
    inlines = (CourseLessonInline,)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        refresh_admin_course_snapshot(obj.course)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        refresh_admin_course_snapshot(form.instance.course)

    def delete_model(self, request, obj):
        course = obj.course
        super().delete_model(request, obj)
        refresh_admin_course_snapshot(course)


@admin.register(models.CourseLesson)
class CourseLessonAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson_key", "module", "content_type", "position", "is_free_preview", "is_published")
    list_filter = ("content_type", "is_free_preview", "is_published")
    search_fields = ("title", "lesson_key", "module__title", "module__course__title")
    form = CourseLessonAdminForm
    fieldsets = (
        (
            "Lesson content",
            {
                "fields": (
                    "module",
                    "position",
                    "lesson_key",
                    "title",
                    "summary",
                    "content_type",
                    "duration_label",
                    "asset_url",
                    "media_file",
                    "metadata",
                )
            },
        ),
        (
            "Publishing",
            {
                "fields": (
                    "is_free_preview",
                    "is_published",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        refresh_admin_course_snapshot(obj.module.course)

    def delete_model(self, request, obj):
        course = obj.module.course
        super().delete_model(request, obj)
        refresh_admin_course_snapshot(course)


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
    list_display = ("course", "email", "status", "progress_percent", "current_lesson", "last_activity_at", "created_at")
    search_fields = ("email", "course__title")
    list_filter = ("status",)


@admin.register(models.LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "lesson", "status", "progress_percent", "last_position_seconds", "last_viewed_at")
    search_fields = ("enrollment__email", "lesson__title", "lesson__module__course__title")
    list_filter = ("status", "lesson__content_type")


@admin.register(models.LessonQuestion)
class LessonQuestionAdmin(admin.ModelAdmin):
    list_display = ("question", "course", "lesson", "timestamp_seconds", "position", "is_published")
    list_filter = ("is_published", "course__category")
    search_fields = ("question", "answer", "course__title", "lesson__title")
    autocomplete_fields = ("course", "lesson")
    fields = ("course", "lesson", "position", "timestamp_seconds", "question", "answer", "is_published", "metadata")


@admin.register(models.QuestionCompletion)
class QuestionCompletionAdmin(admin.ModelAdmin):
    list_display = ("email", "course", "lesson", "question_key", "completed", "completed_at", "updated_at")
    list_filter = ("completed", "course__category")
    search_fields = ("email", "question_key", "course__title", "lesson__title")


@admin.register(models.WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("course", "email", "created_at")
    search_fields = ("email", "course__title")


@admin.register(models.UserCourseNote)
class UserCourseNoteAdmin(admin.ModelAdmin):
    list_display = ("course", "email", "updated_at")
    search_fields = ("email", "course__title", "notes")


@admin.register(models.NotebookNote)
class NotebookNoteAdmin(admin.ModelAdmin):
    list_display = ("title", "email", "course", "lesson", "category", "pinned", "is_deleted", "updated_at")
    list_filter = ("category", "pinned", "is_deleted", "course__category")
    search_fields = ("title", "body_preview", "email", "course__title", "lesson__title")
    readonly_fields = ("version", "created_at", "updated_at", "last_synced_at")


@admin.register(models.NotebookNoteVersion)
class NotebookNoteVersionAdmin(admin.ModelAdmin):
    list_display = ("note", "version", "title", "category", "created_at")
    search_fields = ("note__email", "title", "body_preview")
    list_filter = ("category",)


@admin.register(models.NotebookAttachment)
class NotebookAttachmentAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "course", "note", "content_type", "size", "created_at")
    search_fields = ("name", "email", "course__title", "note__title")
    list_filter = ("content_type", "course__category")


@admin.register(models.AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("email", "course", "lesson", "status", "grade", "updated_at")
    list_filter = ("status", "course__category")
    search_fields = ("email", "course__title", "lesson__title", "response", "feedback")


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
