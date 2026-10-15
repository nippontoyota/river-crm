from django.db import migrations


def sync_sales_status(apps, schema_editor):
    Lead = apps.get_model("leads", "Lead")
    for status, outcome in (("BOOKED", "BOOKED"), ("WON", "RETAILED"), ("LOST", "LOST")):
        Lead.objects.using(schema_editor.connection.alias).filter(status=status).exclude(
            sales_outcome=outcome,
        ).update(sales_outcome=outcome)


class Migration(migrations.Migration):
    dependencies = [("leads", "0023_separate_walkin_and_booked")]
    operations = [migrations.RunPython(sync_sales_status, migrations.RunPython.noop)]
