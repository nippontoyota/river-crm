from django.db import migrations
from django.utils import timezone


def activate(apps, schema_editor):
    apps.get_model("feedback", "FeedbackState").objects.using(schema_editor.connection.alias).get_or_create(
        pk=1, defaults={"activated_at": timezone.now()})


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0001_initial"),
        ("notifications", "0003_notification_dedupe_key_notification_feedback_task_and_more"),
    ]
    operations = [migrations.RunPython(activate, migrations.RunPython.noop)]
