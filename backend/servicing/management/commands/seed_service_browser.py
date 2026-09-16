from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from leads.models import Lead, SystemConfig


class Command(BaseCommand):
    help = "Seed the isolated service browser test database."

    def handle(self, *args, **options):
        if not settings.DEBUG or str(settings.DATABASES["default"]["NAME"]) != "/tmp/crm-service-browser.sqlite3":
            raise CommandError("Use DEBUG=true and DATABASE_URL=sqlite:////tmp/crm-service-browser.sqlite3 only.")
        SystemConfig.objects.update_or_create(pk=1, defaults={"lists": {"branches": ["Kochi", "Thrissur"], "models": ["River Indie"], "sources": ["Website"], "colorVariants": ["Blue"]}})
        users = {}
        for name, role, branch in [("admin", "ADMIN", ""), ("ce", "CRE", "Kochi"), ("so", "SO", "Kochi"), ("service", "SERVICE", "Kochi"), ("other", "SERVICE", "Thrissur"), ("ceo", "CEO", "")]:
            user, _ = User.objects.update_or_create(email=f"{name}@service-browser.test", defaults={"first_name": name.title(), "role": role, "location": branch, "is_active": True})
            user.set_password("ServiceBrowser123!")
            user.save()
            users[name] = user
        lead, _ = Lead.objects.get_or_create(phone="9876543210", defaults={"name": "Anjali Service Rider", "email": "anjali@example.test", "model_interest": "River Indie", "source": "Website", "branch": "Kochi", "status": "WALKIN", "sales_outcome": "BOOKED", "assigned_so": users["ce"], "assigned_ps": users["so"]})
        Lead.objects.get_or_create(phone="9876543211", defaults={"name": "New Enquiry", "model_interest": "River Indie", "source": "Website", "branch": "Kochi", "assigned_so": users["ce"]})
        self.stdout.write(f"Service browser users ready; sales lead #{lead.pk}.")
