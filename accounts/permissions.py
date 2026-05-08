from __future__ import annotations

from typing import Any


PUBLIC_SIGNUP_ROLES = {"student", "instructor"}

ROLE_CAPABILITIES: dict[str, dict[str, bool]] = {
    "student": {
        "canEnrollCourses": True,
        "canWatchLessons": True,
        "canSubmitAssignments": True,
        "canTakeQuizzes": True,
        "canLeaveReviews": True,
        "canCreateCourses": False,
        "canUploadLessons": False,
        "canManageStudents": False,
        "canViewInstructorAnalytics": False,
        "canAccessAdminDashboard": False,
        "canAccessAdminModeration": False,
        "canConfigurePlatform": False,
    },
    "instructor": {
        "canEnrollCourses": True,
        "canWatchLessons": True,
        "canSubmitAssignments": True,
        "canTakeQuizzes": True,
        "canLeaveReviews": True,
        "canCreateCourses": True,
        "canUploadLessons": True,
        "canManageStudents": True,
        "canViewInstructorAnalytics": True,
        "canAccessAdminDashboard": False,
        "canAccessAdminModeration": False,
        "canConfigurePlatform": False,
    },
    "admin": {
        "canEnrollCourses": True,
        "canWatchLessons": True,
        "canSubmitAssignments": True,
        "canTakeQuizzes": True,
        "canLeaveReviews": True,
        "canCreateCourses": True,
        "canUploadLessons": True,
        "canManageStudents": True,
        "canViewInstructorAnalytics": True,
        "canAccessAdminDashboard": True,
        "canAccessAdminModeration": True,
        "canConfigurePlatform": True,
    },
    "support": {
        "canEnrollCourses": False,
        "canWatchLessons": False,
        "canSubmitAssignments": False,
        "canTakeQuizzes": False,
        "canLeaveReviews": False,
        "canCreateCourses": False,
        "canUploadLessons": False,
        "canManageStudents": False,
        "canViewInstructorAnalytics": True,
        "canAccessAdminDashboard": False,
        "canAccessAdminModeration": True,
        "canConfigurePlatform": False,
    },
}


def user_role(user) -> str:
    role = getattr(user, "role", "")
    if role:
        return str(role)
    return "admin" if getattr(user, "is_staff", False) else "student"


def user_has_role(user, *roles: str) -> bool:
    if not user:
        return False
    return user_role(user) in set(roles)


def has_any_perm(user, *permissions: str) -> bool:
    if not user:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return any(user.has_perm(permission) for permission in permissions)


def is_public_signup_role(role: str) -> bool:
    return str(role or "").strip().lower() in PUBLIC_SIGNUP_ROLES


def can_manage_instructor_content(user) -> bool:
    return bool(
        user
        and (
            user_has_role(user, "instructor", "admin")
            or has_any_perm(user, "academy.add_course", "academy.change_course")
        )
    )


def can_access_admin_dashboard(user) -> bool:
    return bool(
        user
        and (
            getattr(user, "is_staff", False)
            or user_has_role(user, "admin")
            or has_any_perm(user, "academy.view_authauditlog")
        )
    )


def can_access_admin_moderation(user) -> bool:
    return bool(
        user
        and (
            user_has_role(user, "admin", "support")
            or has_any_perm(user, "academy.moderate_courses")
        )
    )


def can_configure_platform(user) -> bool:
    return bool(
        user
        and (
            user_has_role(user, "admin")
            or has_any_perm(user, "academy.configure_platform")
        )
    )


def build_user_capabilities(user) -> dict[str, Any]:
    role = user_role(user)
    capabilities = dict(ROLE_CAPABILITIES.get(role, ROLE_CAPABILITIES["student"]))
    capabilities["canAccessAdminDashboard"] = can_access_admin_dashboard(user)
    capabilities["canAccessAdminModeration"] = can_access_admin_moderation(user)
    capabilities["canConfigurePlatform"] = can_configure_platform(user)
    capabilities["canCreateCourses"] = can_manage_instructor_content(user)
    capabilities["canUploadLessons"] = capabilities["canCreateCourses"]
    capabilities["canManageStudents"] = capabilities["canCreateCourses"]
    capabilities["canViewInstructorAnalytics"] = capabilities["canCreateCourses"] or capabilities["canViewInstructorAnalytics"]
    return capabilities
