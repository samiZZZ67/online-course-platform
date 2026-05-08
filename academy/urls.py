from django.urls import path, re_path

from . import views


app_name = "academy"


urlpatterns = [
    path("", views.index, name="index"),
    path("index.html", views.index, name="index-file"),
    path("frontend-auth.js", views.frontend_auth_script, name="frontend-auth-script"),
    path("api/health", views.health, name="health"),
    path("api/auth/login", views.auth_login, name="auth-login"),
    path("api/auth/signup", views.auth_signup, name="auth-signup"),
    path("api/auth/refresh", views.auth_refresh, name="auth-refresh"),
    path("api/auth/verify-email/request", views.auth_verify_email_request, name="auth-verify-email-request"),
    path("api/auth/verify-email/confirm", views.auth_verify_email_confirm, name="auth-verify-email-confirm"),
    path("api/auth/me", views.auth_me, name="auth-me"),
    path("api/auth/logout", views.auth_logout, name="auth-logout"),
    path("api/auth/oauth/start", views.auth_oauth_start, name="auth-oauth-start"),
    path("api/auth/password/reset-request", views.auth_password_reset_request, name="auth-password-reset-request"),
    path("api/auth/password/reset-confirm", views.auth_password_reset_confirm, name="auth-password-reset-confirm"),
    path("api/newsletter/subscribe", views.newsletter_subscribe, name="newsletter-subscribe"),
    path("api/enrollments/progress", views.enrollment_progress, name="enrollment-progress"),
    path("api/enrollments", views.enrollments, name="enrollments"),
    path("api/wishlist", views.wishlist, name="wishlist"),
    path("api/ai/tutor", views.ai_tutor, name="ai-tutor"),
    path("api/courses/share", views.course_share, name="course-share"),
    path("api/gifts", views.gifts, name="gifts"),
    path("api/coupons/validate", views.coupon_validate, name="coupon-validate"),
    path("api/notes", views.notes, name="notes"),
    path("api/notifications", views.notifications, name="notifications"),
    path("api/instructor/courses/drafts", views.instructor_drafts, name="instructor-drafts"),
    path("api/instructor/courses", views.instructor_courses, name="instructor-courses"),
    path("api/instructor/courses/thumbnail", views.instructor_thumbnail, name="instructor-thumbnail"),
    path("api/dashboard/tab", views.dashboard_tab, name="dashboard-tab"),
    path("api/certificates/share", views.certificate_share, name="certificate-share"),
    path("api/certificates/preview", views.certificate_preview, name="certificate-preview"),
    path("api/courses/<slug:course_id>/resources", views.course_resources, name="course-resources"),
    path("api/courses/<slug:course_id>", views.course_detail, name="course-detail"),
    path("api/courses", views.course_list, name="course-list"),
    re_path(r"^api/.*$", views.api_not_found, name="api-not-found"),
]
