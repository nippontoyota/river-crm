from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        CRE = "CRE", "CRE"
        SALES_OFFICER = "SO", "PS/SO"
        SALES_MANAGER = "SALES_MANAGER", "Sales Manager"
        RECEPTIONIST = "RECEPTIONIST", "Receptionist"
        COMPLAINTS = "COMPLAINTS", "Complaints department"

    username = None
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    location = models.CharField(max_length=100, blank=True, db_index=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CRE)
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []
    objects = UserManager()

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_sales_manager(self):
        return self.role == self.Role.SALES_MANAGER

    @property
    def lifecycle_status(self):
        if self.deleted_at:
            return "DELETED"
        return "ACTIVE" if self.is_active else "DISABLED"

    @property
    def history_display_name(self):
        name = self.get_full_name() or self.email
        return f"{name} · Deleted" if self.deleted_at else name


class UserLifecycleEvent(models.Model):
    class Action(models.TextChoices):
        DISABLED = "DISABLED", "Disabled"
        ENABLED = "ENABLED", "Enabled"
        DELETED = "DELETED", "Deleted"

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="lifecycle_events")
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="performed_lifecycle_events")
    action = models.CharField(max_length=10, choices=Action.choices)
    reason = models.CharField(max_length=500, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
