from django.db import migrations, models


def protect_walkin_source(apps, schema_editor):
    SystemConfig = apps.get_model("leads", "SystemConfig")
    for config in SystemConfig.objects.all():
        lists = dict(config.lists or {})
        sources = ["WALKIN"]
        seen = {"walkin"}
        for value in lists.get("sources", []) if isinstance(lists.get("sources", []), list) else []:
            source = str(value).strip()
            key = "".join(character for character in source.casefold() if character.isalnum())
            if source and key not in seen:
                seen.add(key)
                sources.append(source)
        lists["sources"] = sources
        config.lists = lists
        config.save(update_fields=["lists"])


class Migration(migrations.Migration):
    dependencies = [("leads", "0012_offboarding_state")]

    operations = [
        migrations.AlterField(
            model_name="lead",
            name="source",
            field=models.CharField(default="UNKNOWN", max_length=100),
        ),
        migrations.RunPython(protect_walkin_source, migrations.RunPython.noop),
    ]
