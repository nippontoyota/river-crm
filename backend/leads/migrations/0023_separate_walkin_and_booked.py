from django.db import migrations, models
from django.db.models import Q


STATUS_CHOICES = [
    ("FRESH", "Fresh"),
    ("RNR", "RNR"),
    ("SWITCHED_OFF", "Switched off"),
    ("CALLBACK", "Callback Scheduled"),
    ("PENDING", "Pending"),
    ("QUALIFIED", "Qualified"),
    ("UNQUALIFIED", "Unqualified"),
    ("WALKIN", "Walk-in"),
    ("BOOKED", "Booked"),
    ("WON", "Won"),
    ("LOST", "Lost"),
]


def separate_walkin_and_booked(apps, schema_editor):
    Lead = apps.get_model("leads", "Lead")
    CallLog = apps.get_model("leads", "CallLog")
    OperationEvent = apps.get_model("ceo", "OperationEvent")
    db = schema_editor.connection.alias

    Lead.objects.using(db).filter(sales_outcome="BOOKED").exclude(
        status__in=["WON", "LOST", "UNQUALIFIED"],
    ).update(status="BOOKED")
    calls = list(CallLog.objects.using(db).filter(
        Q(outcome__iexact="Booking Done") | Q(outcome__iexact="Already Booked"),
    ).exclude(status__in=["WON", "LOST", "UNQUALIFIED"]))
    CallLog.objects.using(db).filter(pk__in=[call.pk for call in calls]).update(status="BOOKED")
    for call in calls:
        event = OperationEvent.objects.using(db).filter(source_key=f"call:{call.pk}").first()
        if event:
            event.after = {**event.after, "status": "BOOKED"}
            event.snapshot = {**event.snapshot, "status": "BOOKED"}
            event.save(update_fields=["after", "snapshot"])


class Migration(migrations.Migration):
    dependencies = [("leads", "0022_already_booked_is_booking")]
    operations = [
        migrations.AlterField(
            model_name="lead",
            name="status",
            field=models.CharField(choices=STATUS_CHOICES, db_index=True, default="FRESH", max_length=20),
        ),
        migrations.AlterField(
            model_name="calllog",
            name="status",
            field=models.CharField(choices=STATUS_CHOICES, max_length=20),
        ),
        migrations.RunPython(separate_walkin_and_booked, migrations.RunPython.noop),
    ]
