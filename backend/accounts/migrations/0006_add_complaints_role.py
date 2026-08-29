from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_alter_user_role"),
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
                    ("RECEPTIONIST", "Receptionist"),
                    ("COMPLAINTS", "Complaints department"),
                ],
                default="CRE",
                max_length=20,
            ),
        ),
    ]
