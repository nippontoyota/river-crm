from django.db import migrations, models
from django.contrib.auth.hashers import make_password


DEMO_PASSWORD = "Demo@123456"


def seed_demo_team(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    locations = {
        "member@revera.test": "Kochi",
        "ps@revera.test": "Kochi",
        "meera.iyer.demo@revera.test": "Kochi",
        "kabir.khan.demo@revera.test": "Kozhikode",
        "ananya.reddy.demo@revera.test": "Thrissur",
        "vivaan.patel.demo@revera.test": "Trivandrum",
        "aarav.sharma.demo@revera.test": "Kannur",
    }
    for email, location in locations.items():
        User.objects.filter(email=email).update(location=location)

    rows = [
        ("nisha.menon.demo@revera.test", "Nisha", "Menon", "CRE", "Kochi"),
        ("rohit.nair.demo@revera.test", "Rohit", "Nair", "CRE", "Kozhikode"),
        ("diya.varma.demo@revera.test", "Diya", "Varma", "CRE", "Kannur"),
        ("arjun.nair.demo@revera.test", "Arjun", "Nair", "SO", "Kochi"),
        ("sara.jose.demo@revera.test", "Sara", "Jose", "SO", "Kozhikode"),
        ("devika.pillai.demo@revera.test", "Devika", "Pillai", "SO", "Thrissur"),
        ("imran.sha.demo@revera.test", "Imran", "Sha", "SO", "Trivandrum"),
        ("ravi.menon.demo@revera.test", "Ravi", "Menon", "SO", "Kannur"),
    ]
    for email, first_name, last_name, role, location in rows:
        User.objects.update_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "role": role,
                "location": location,
                "is_active": True,
                "password": make_password(DEMO_PASSWORD),
            },
        )


def unseed_demo_team(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(email__in=[
        "nisha.menon.demo@revera.test",
        "rohit.nair.demo@revera.test",
        "diya.varma.demo@revera.test",
        "arjun.nair.demo@revera.test",
        "sara.jose.demo@revera.test",
        "devika.pillai.demo@revera.test",
        "imran.sha.demo@revera.test",
        "ravi.menon.demo@revera.test",
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_cre_and_ps_roles"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="location",
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.RunPython(seed_demo_team, unseed_demo_team),
    ]
