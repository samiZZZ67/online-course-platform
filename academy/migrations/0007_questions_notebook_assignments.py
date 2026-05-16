# Generated manually for integrated questions, notebook notes, and assignments.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academy", "0006_course_includes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LessonQuestion",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("question", models.CharField(max_length=500)),
                ("answer", models.TextField(blank=True)),
                ("timestamp_seconds", models.PositiveIntegerField(default=0)),
                ("position", models.PositiveIntegerField(db_index=True, default=1)),
                ("is_published", models.BooleanField(db_index=True, default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lesson_questions", to="academy.course")),
                ("lesson", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="questions", to="academy.courselesson")),
            ],
            options={
                "ordering": ["lesson__module__position", "lesson__position", "position", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="NotebookNote",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(db_index=True, default="demo@skillforge.local", max_length=254)),
                ("title", models.CharField(blank=True, max_length=255)),
                ("encrypted_body", models.TextField(blank=True)),
                ("body_preview", models.TextField(blank=True)),
                ("category", models.CharField(db_index=True, default="General", max_length=120)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("pinned", models.BooleanField(db_index=True, default=False)),
                ("timestamp_seconds", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("shared_with", models.JSONField(blank=True, default=list)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notebook_notes", to="academy.course")),
                ("lesson", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notebook_notes", to="academy.courselesson")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notebooknotes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-pinned", "-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="NotebookNoteVersion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("title", models.CharField(blank=True, max_length=255)),
                ("encrypted_body", models.TextField(blank=True)),
                ("body_preview", models.TextField(blank=True)),
                ("category", models.CharField(default="General", max_length=120)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("timestamp_seconds", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("note", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="versions", to="academy.notebooknote")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="NotebookAttachment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(db_index=True, default="demo@skillforge.local", max_length=254)),
                ("file", models.FileField(upload_to="notebook-attachments/%Y/%m/")),
                ("name", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=120)),
                ("size", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notebook_attachments", to="academy.course")),
                ("note", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="attachments", to="academy.notebooknote")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notebookattachments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="QuestionCompletion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(db_index=True, default="demo@skillforge.local", max_length=254)),
                ("question_key", models.CharField(db_index=True, max_length=180)),
                ("completed", models.BooleanField(default=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="question_completions", to="academy.course")),
                ("lesson", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="question_completions", to="academy.courselesson")),
                ("question", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="completions", to="academy.lessonquestion")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="questioncompletions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="AssignmentSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(db_index=True, default="demo@skillforge.local", max_length=254)),
                ("response", models.TextField(blank=True)),
                ("status", models.CharField(db_index=True, default="draft", max_length=32)),
                ("grade", models.CharField(blank=True, max_length=32)),
                ("feedback", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignment_submissions", to="academy.course")),
                ("lesson", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignment_submissions", to="academy.courselesson")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assignmentsubmissions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="questioncompletion",
            constraint=models.UniqueConstraint(fields=("email", "course", "question_key"), name="unique_question_completion_email_course_key"),
        ),
        migrations.AddConstraint(
            model_name="assignmentsubmission",
            constraint=models.UniqueConstraint(fields=("email", "lesson"), name="unique_assignment_submission_email_lesson"),
        ),
    ]
