from django.db import migrations


def retire_walkin_status(apps, schema_editor):
    Lead = apps.get_model("leads", "Lead")
    legacy = Lead.objects.using(schema_editor.connection.alias).filter(status="WALKIN")
    # Preserve recorded sales progress and acquisition source. A walk-in alone
    # is an enquiry handed to PS, not evidence of a booking.
    for outcome, status in (("BOOKED", "BOOKED"), ("RETAILED", "WON"), ("LOST", "LOST"), ("PENDING", "QUALIFIED")):
        legacy.filter(sales_outcome=outcome).update(status=status)
    # Call logs and audit history intentionally retain their original values.


class Migration(migrations.Migration):
    dependencies = [("leads", "0024_sync_explicit_sales_status")]
    operations = [migrations.RunPython(retire_walkin_status, migrations.RunPython.noop)]
