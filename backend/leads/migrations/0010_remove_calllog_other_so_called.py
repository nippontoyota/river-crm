# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0009_lead_profession'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='calllog',
            name='other_so_called',
        ),
    ]
