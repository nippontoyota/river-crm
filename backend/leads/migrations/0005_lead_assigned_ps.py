from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("leads", "0004_lead_pending_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="assigned_ps",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="ps_leads", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["assigned_ps", "status"], name="leads_lead_assigne_78bf94_idx"),
        ),
    ]
