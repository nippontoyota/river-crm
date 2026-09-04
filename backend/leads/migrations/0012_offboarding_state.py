from django.db import migrations, models


CLOSED = ["WON", "LOST", "UNQUALIFIED"]


def queue_inactive_work(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Lead = apps.get_model("leads", "Lead")
    FollowUp = apps.get_model("leads", "FollowUp")
    inactive_cre = User.objects.filter(role="CRE", is_active=False).values_list("id", flat=True)
    inactive_so = User.objects.filter(role="SO", is_active=False).values_list("id", flat=True)
    Lead.objects.exclude(status__in=CLOSED).filter(assigned_so_id__in=inactive_cre).update(assigned_so=None, needs_cre_reassignment=True)
    Lead.objects.exclude(status__in=CLOSED).filter(assigned_ps_id__in=inactive_so).update(assigned_ps=None, needs_so_reassignment=True)
    FollowUp.objects.filter(resolved_at__isnull=True, so__is_active=False).update(reminder_held=True)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_user_lifecycle"), ("leads", "0011_calllog_other_so")]

    operations = [
        migrations.AddField(model_name="lead", name="needs_cre_reassignment", field=models.BooleanField(db_index=True, default=False)),
        migrations.AddField(model_name="lead", name="needs_so_reassignment", field=models.BooleanField(db_index=True, default=False)),
        migrations.AddField(model_name="followup", name="reminder_held", field=models.BooleanField(db_index=True, default=False)),
        migrations.RunPython(queue_inactive_work, migrations.RunPython.noop),
    ]
