from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0002_leadqualification_calllog_outcome_lead_branch_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lead",
            name="status",
            field=models.CharField(
                choices=[
                    ("FRESH", "Fresh"),
                    ("RNR", "RNR"),
                    ("SWITCHED_OFF", "Switched off"),
                    ("CALLBACK", "Callback Scheduled"),
                    ("QUALIFIED", "Qualified"),
                    ("UNQUALIFIED", "Unqualified"),
                    ("WALKIN", "Walk-in Booked"),
                    ("WON", "Won"),
                    ("LOST", "Lost"),
                ],
                db_index=True,
                default="FRESH",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="calllog",
            name="status",
            field=models.CharField(
                choices=[
                    ("FRESH", "Fresh"),
                    ("RNR", "RNR"),
                    ("SWITCHED_OFF", "Switched off"),
                    ("CALLBACK", "Callback Scheduled"),
                    ("QUALIFIED", "Qualified"),
                    ("UNQUALIFIED", "Unqualified"),
                    ("WALKIN", "Walk-in Booked"),
                    ("WON", "Won"),
                    ("LOST", "Lost"),
                ],
                max_length=20,
            ),
        ),
    ]
