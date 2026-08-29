import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from accounts.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from leads.views import SystemConfigView

factory = APIRequestFactory()
request = factory.get('/api/leads/system-config/')
cre = User.objects.filter(role=User.Role.CRE).first()
force_authenticate(request, user=cre)

view = SystemConfigView.as_view()
response = view(request)
print("Status:", response.status_code)
print("Data:", response.data)
