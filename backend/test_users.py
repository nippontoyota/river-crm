import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from accounts.models import User
sos = User.objects.filter(role=User.Role.SALES_OFFICER)
print(f"Total SOs: {sos.count()}")
for so in sos:
    print(f"SO: {so.email}, is_active: {so.is_active}, location: '{so.location}'")
