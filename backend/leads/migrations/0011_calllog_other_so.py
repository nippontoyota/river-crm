# Generated manually to match the current CallLog model.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leads", "0010_remove_calllog_other_so_called"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="calllog",
            name="other_so",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="other_so_call_logs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
