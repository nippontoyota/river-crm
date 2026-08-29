from django.db import migrations, models


STATUS_CHOICES = [
    ("FRESH", "Fresh"),
    ("RNR", "RNR"),
    ("SWITCHED_OFF", "Switched off"),
    ("CALLBACK", "Callback Scheduled"),
    ("PENDING", "Pending"),
    ("QUALIFIED", "Qualified"),
    ("UNQUALIFIED", "Unqualified"),
    ("WALKIN", "Walk-in Booked"),
    ("WON", "Won"),
    ("LOST", "Lost"),
]


class Migration(migrations.Migration):
    dependencies = [("leads", "0003_lead_switched_off_status")]

    operations = [
        migrations.AlterField(model_name="lead", name="status", field=models.CharField(choices=STATUS_CHOICES, db_index=True, default="FRESH", max_length=20)),
        migrations.AlterField(model_name="calllog", name="status", field=models.CharField(choices=STATUS_CHOICES, max_length=20)),
    ]
