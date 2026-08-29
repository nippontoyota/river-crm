from django.db import migrations, models


def move_existing_so_to_cre(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="SO").update(role="CRE")


def move_cre_back_to_so(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="CRE").update(role="SO")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_alter_user_managers"),
    ]

    operations = [
        migrations.RunPython(move_existing_so_to_cre, move_cre_back_to_so),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(choices=[("ADMIN", "Admin"), ("CRE", "CRE"), ("SO", "PS/SO")], default="CRE", max_length=10),
        ),
    ]
