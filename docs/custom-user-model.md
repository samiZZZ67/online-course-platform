# SkillForge Custom User Model Design

## Objective

Replace Django's default user model with a custom user model that fits a learning platform.

This design covers:

- UUID primary key
- email login
- username support
- role support
- profile data
- verification status
- account status
- security and audit timestamps

## Recommended Django Approach

Use:

- `AbstractBaseUser`
- `PermissionsMixin`

Create a dedicated `accounts` app and define:

- `accounts.models.User`
- `accounts.managers.UserManager`

Project setting:

- `AUTH_USER_MODEL = "accounts.User"`

Why this approach:

- full control over identity fields
- email-first authentication
- clean role support
- compatible with Django admin, permissions, and future JWT auth

## Core Model

Recommended model:

- `accounts.User`

Recommended base class:

- `class User(AbstractBaseUser, PermissionsMixin):`

## Identity Design

### Primary key

- `id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`

Why:

- safer public identifiers
- easier API exposure than integer ids
- better fit for distributed integrations later

### Email

- required
- unique
- normalized to lowercase
- used as the main login credential

Recommended field:

- `email = models.EmailField(unique=True, db_index=True)`

### Username

- supported
- optional at account creation
- unique when present
- used for profile URLs, mentions, or public display handles
- not used as the main login identifier

Recommended field:

- `username = models.CharField(max_length=32, unique=True, null=True, blank=True)`

Recommended rule:

- treat blank usernames as `NULL`
- reserve username validation for letters, numbers, underscore, and dot

### Login rule

- primary login: `email`
- optional fallback login by username can be added later, but not in the first auth implementation

Django settings:

- `USERNAME_FIELD = "email"`
- `REQUIRED_FIELDS = []`

## Role Design

### Required roles

- `student`
- `instructor`
- `admin`

Recommended expansion-ready enum:

- `student`
- `instructor`
- `admin`
- `support`

Recommended field:

- `role = models.CharField(max_length=24, choices=RoleChoices, default="student", db_index=True)`

Rules:

- `role` is the coarse application role
- Django permissions and groups remain the source of truth for authorization
- `admin` role should align with `is_staff=True`

## Profile Data

### Avatar

Recommended field:

- `avatar = models.URLField(max_length=500, blank=True)`

Recommended future option:

- switch to `ImageField` later if local upload or cloud media storage is added

### Bio

Recommended field:

- `bio = models.TextField(blank=True)`

Recommended limit:

- enforce a soft application-level max around `500-1000` characters

### Display helpers

Recommended fields:

- `first_name = models.CharField(max_length=150, blank=True)`
- `last_name = models.CharField(max_length=150, blank=True)`

Recommended computed property:

- `full_name`

## Verification Status

Recommended fields:

- `is_email_verified = models.BooleanField(default=False, db_index=True)`
- `email_verified_at = models.DateTimeField(null=True, blank=True)`

Rule:

- `email_verified_at` is the authoritative audit field
- `is_email_verified` is the fast filter flag
- keep both values in sync

## Security Fields

### Password hashing

- rely on Django's built-in password hashing through `AbstractBaseUser`
- never store raw passwords

### Authentication state

Recommended fields:

- `is_active = models.BooleanField(default=True, db_index=True)`
- `is_staff = models.BooleanField(default=False, db_index=True)`
- `is_superuser` comes from `PermissionsMixin`

### Password and session audit support

Recommended field:

- `last_password_changed_at = models.DateTimeField(null=True, blank=True)`

Why:

- revoke old refresh tokens after password changes
- audit security-sensitive events

## Audit and Metadata Fields

Required metadata from your brief:

- `date_joined`
- `last_login`
- account status

Recommended fields:

- `date_joined = models.DateTimeField(default=timezone.now, db_index=True)`
- `last_login` is inherited from `AbstractBaseUser`
- `created_at = models.DateTimeField(auto_now_add=True)`
- `updated_at = models.DateTimeField(auto_now=True)`

Recommended account status field:

- `status = models.CharField(max_length=24, choices=StatusChoices, default="active", db_index=True)`

Recommended statuses:

- `active`
- `pending_verification`
- `suspended`
- `deactivated`

Rule:

- `is_active` controls whether Django allows authentication
- `status` explains business state in the LMS

## Recommended Final Field Set

Recommended model fields:

- `id`
- `email`
- `username`
- `first_name`
- `last_name`
- `role`
- `avatar`
- `bio`
- `is_email_verified`
- `email_verified_at`
- `status`
- `is_active`
- `is_staff`
- `is_superuser`
- `date_joined`
- `last_login`
- `last_password_changed_at`
- `created_at`
- `updated_at`

## Manager Design

Create a custom `UserManager`.

Required methods:

- `create_user(email, password=None, **extra_fields)`
- `create_superuser(email, password=None, **extra_fields)`

Manager responsibilities:

- normalize email
- enforce email presence
- set default role to `student`
- set `is_staff` and `is_superuser` correctly for admins
- set a default username if the product later requires one

Recommended superuser rules:

- `role="admin"`
- `is_staff=True`
- `is_superuser=True`
- `is_active=True`
- `is_email_verified=True`

## Model Behavior

Recommended instance helpers:

- `get_full_name()`
- `get_short_name()`
- `display_name` property
- `mark_email_verified()`
- `mark_password_changed()`

Recommended `__str__`:

- email if available
- otherwise UUID

## Database Constraints and Indexes

Recommended constraints:

- unique email
- unique username when not null

Recommended indexes:

- `email`
- `username`
- `role`
- `status`
- `is_active`
- `is_email_verified`
- `date_joined`

Recommended validation:

- username format validation
- email normalization before save

## Admin Behavior

Create a custom admin class for the new model.

Recommended admin behavior:

- searchable by email, username, first name, last name
- filterable by role, status, staff, active, verified
- list display for identity and security state
- password change handled by Django admin forms

Recommended list columns:

- `email`
- `username`
- `role`
- `status`
- `is_email_verified`
- `is_staff`
- `is_active`
- `date_joined`
- `last_login`

## Recommended Sample Shape

```python
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email).strip().lower()
        extra_fields.setdefault("role", User.Role.STUDENT)
        extra_fields.setdefault("status", User.Status.PENDING_VERIFICATION)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("status", User.Status.ACTIVE)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_email_verified", True)
        return self.create_user(email, password, **extra_fields)


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
    username = models.CharField(max_length=32, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=24, choices=Role.choices, default=Role.STUDENT, db_index=True)
    avatar = models.URLField(max_length=500, blank=True)
    bio = models.TextField(blank=True)
    is_email_verified = models.BooleanField(default=False, db_index=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING_VERIFICATION, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_staff = models.BooleanField(default=False, db_index=True)
    date_joined = models.DateTimeField(default=timezone.now, db_index=True)
    last_password_changed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
```

## Migration Strategy

This part matters because the project currently uses Django's default `User`.

Recommended path:

1. Create a new `accounts` app.
2. Define the custom `User` model before adding more auth migrations.
3. Set `AUTH_USER_MODEL = "accounts.User"`.
4. Update all foreign keys that currently point to `settings.AUTH_USER_MODEL` to stay aligned with the new model.
5. Rebuild or replace early migrations if the project is still in a safe reset window.
6. Migrate seed data and admin users into the new table.
7. Update auth services, admin, tests, and JWT code to use the custom model.

Important note:

- because this project is still early, a migration reset is safer than trying to preserve a lot of legacy auth state

## Compatibility With The LMS

This design supports:

- student enrollments
- instructor dashboards and course ownership
- admin moderation and platform access
- verified-email flows
- JWT access and rotating refresh tokens
- public profile extensions later

## Final Recommendation

Use a custom `accounts.User` model built on `AbstractBaseUser` and `PermissionsMixin` with:

- UUID primary key
- unique email as login identity
- optional unique username
- role field for `student`, `instructor`, and `admin`
- avatar and bio for profile data
- email verification fields
- account status field
- Django-native password hashing
- joined, login, and audit timestamps

This is the right foundation for the LMS and should be done before we implement the next authentication layer.
