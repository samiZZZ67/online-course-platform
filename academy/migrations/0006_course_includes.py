# Generated manually for course include buttons.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academy", "0005_backfill_course_structure"),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="includes",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
