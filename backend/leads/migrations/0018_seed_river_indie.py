from django.db import migrations


def seed_river_indie(apps, schema_editor):
    # Current model: https://www.rideriver.com/indie (verified September 2026).
    Config = apps.get_model("leads", "SystemConfig")
    for config in Config.objects.using(schema_editor.connection.alias).all():
        lists = dict(config.lists or {})
        models = list(lists.get("models") or [])
        if not any(str(model).strip().casefold() == "river indie" for model in models):
            lists["models"] = [*models, "River Indie"]
            config.lists = lists
            config.save(update_fields=["lists"])


class Migration(migrations.Migration):
    dependencies = [("leads", "0017_test_drive_completion")]
    operations = [migrations.RunPython(seed_river_indie, migrations.RunPython.noop)]
