from django.db import migrations


def queue_inactive_complaints(apps, schema_editor):
    Complaint = apps.get_model("complaints", "Complaint")
    Complaint.objects.filter(status__in=["OPEN", "IN_PROGRESS", "ESCALATED"], assigned_to__is_active=False).update(assigned_to=None)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_user_lifecycle"), ("complaints", "0002_complaint_branch")]
    operations = [migrations.RunPython(queue_inactive_complaints, migrations.RunPython.noop)]
