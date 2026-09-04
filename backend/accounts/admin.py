from django.contrib import admin
from .models import User, UserLifecycleEvent

admin.site.register([User, UserLifecycleEvent])
