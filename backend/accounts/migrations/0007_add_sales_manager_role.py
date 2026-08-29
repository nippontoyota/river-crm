from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_add_complaints_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Admin"),
                    ("CRE", "CRE"),
                    ("SO", "PS/SO"),
                    ("SALES_MANAGER", "Sales Manager"),
                    ("RECEPTIONIST", "Receptionist"),
                    ("COMPLAINTS", "Complaints department"),
                ],
                default="CRE",
                max_length=20,
            ),
        ),
    ]
