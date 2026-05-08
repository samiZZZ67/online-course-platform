from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import User


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
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("username", "first_name", "last_name", "avatar", "bio")}),
        ("Access", {"fields": ("role", "status", "is_email_verified", "email_verified_at")}),
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

