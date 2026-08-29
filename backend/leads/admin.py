from django.contrib import admin
from .models import CallLog, FollowUp, Lead, LeadAudit

admin.site.register([Lead, CallLog, FollowUp, LeadAudit])
