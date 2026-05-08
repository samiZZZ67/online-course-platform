# SkillForge RBAC Design

## Purpose

This document defines the role-based access control model for SkillForge.

The goal is to keep authorization predictable across the LMS while the backend grows.

## Roles

### Student

Can:

- enroll in courses
- watch lessons
- submit assignments
- take quizzes
- leave reviews

Cannot:

- create or edit courses
- manage students
- access the admin dashboard
- configure platform settings

### Instructor

Can:

- create courses
- upload lessons
- manage students inside owned courses
- view instructor analytics
- do everything a student can do

Cannot:

- manage platform settings
- access admin moderation tools
- manage unrelated courses they do not own

### Admin

Can:

- manage all users
- moderate courses
- access platform-wide analytics
- configure platform settings
- access Django admin

## Capability Model

The backend exposes capabilities in the serialized user payload so the runtime frontend bridge can react without changing `index.html`.

Current capability keys:

- `canEnrollCourses`
- `canWatchLessons`
- `canSubmitAssignments`
- `canTakeQuizzes`
- `canLeaveReviews`
- `canCreateCourses`
- `canUploadLessons`
- `canManageStudents`
- `canViewInstructorAnalytics`
- `canAccessAdminDashboard`
- `canAccessAdminModeration`
- `canConfigurePlatform`

## Enforcement Rules

- Authentication is required before role checks.
- Sensitive operations should use both role intent and Django permission hooks where available.
- Instructor actions should also enforce ownership when course ownership exists.
- Admin-only actions should align with `is_staff`, `is_superuser`, or explicit admin capabilities.

## Current Backend Mapping

- RBAC helpers live in `accounts/permissions.py`.
- User serialization includes capability data through `academy/services.py`.
- Instructor-only course routes use the RBAC helper instead of a hard-coded role string.
- Custom Django permissions on `academy.Course` provide a path to richer permission assignment later.

## Near-Term Follow-Up

Next enforcement targets after this design step:

- verified-email gates for high-trust actions
- ownership checks for instructor-managed course edits
- dedicated admin and support moderation endpoints
