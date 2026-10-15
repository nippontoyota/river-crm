from django.db import migrations, transaction
from django.db.models.deletion import ProtectedError


def purge_deleted_test_accounts(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    UserLifecycleEvent = apps.get_model("accounts", "UserLifecycleEvent")
    database = schema_editor.connection.alias
    candidates = User.objects.using(database).filter(deleted_at__isnull=False)
    for user in candidates.iterator():
        if not (user.first_name.casefold().startswith("test") or user.last_name.casefold().startswith("test")):
            continue
        try:
            with transaction.atomic(using=database):
                UserLifecycleEvent.objects.using(database).filter(user_id=user.pk).delete()
                user.delete(using=database)
        except ProtectedError:
            # Preserve customer and audit records if a test account still owns history.
            # Analytics excludes any such already-deleted account.
            continue


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_alter_user_role")]
    operations = [migrations.RunPython(purge_deleted_test_accounts, migrations.RunPython.noop)]
