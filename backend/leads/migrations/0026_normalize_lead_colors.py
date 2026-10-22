from django.db import migrations, models


def normalize_colors(apps, schema_editor):
    Lead = apps.get_model("leads", "Lead")
    Qualification = apps.get_model("leads", "LeadQualification")
    Config = apps.get_model("leads", "SystemConfig")
    alias = schema_editor.connection.alias
    missing = {"", "color not set", "colour not set", "no preference"}
    ids = []
    for pk, variant in Qualification.objects.using(alias).values_list("pk", "variant").iterator(chunk_size=1000):
        if (variant or "").strip().casefold() in missing:
            ids.append(pk)
        if len(ids) >= 1000:
            Qualification.objects.using(alias).filter(pk__in=ids).update(variant="No Preference")
            ids = []
    if ids:
        Qualification.objects.using(alias).filter(pk__in=ids).update(variant="No Preference")
    # Batch inserts without fabricating qualification activity or staff attribution.
    while True:
        ids = list(Lead.objects.using(alias).filter(qualification__isnull=True).values_list("pk", flat=True)[:1000])
        if not ids:
            break
        Qualification.objects.using(alias).bulk_create([Qualification(lead_id=pk, variant="No Preference") for pk in ids])
    for config in Config.objects.using(alias).all():
        lists = dict(config.lists or {})
        lists["colorVariants"] = ["No Preference", *[value for value in lists.get("colorVariants", []) if str(value).strip().casefold() not in missing]]
        config.lists = lists
        config.save(using=alias, update_fields=["lists"])


class Migration(migrations.Migration):
    dependencies = [("leads", "0025_walkin_is_a_source")]
    # Normalization is intentionally retained on rollback; original missing labels are indistinguishable.
    operations = [
        migrations.AlterField(model_name="leadqualification", name="variant", field=models.CharField(max_length=120, blank=True, default="No Preference")),
        migrations.RunPython(normalize_colors, migrations.RunPython.noop),
    ]
