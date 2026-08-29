from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("complaints", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="complaint",
            name="branch",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
