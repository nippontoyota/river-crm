from django.contrib import admin

from .models import Complaint, ComplaintNote


class ComplaintNoteInline(admin.TabularInline):
    model = ComplaintNote
    extra = 0
    readonly_fields = ("author", "created_at")


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("ticket_number", "customer_name", "category", "priority", "status", "logged_by", "created_at")
    list_filter = ("status", "category", "priority", "source")
    search_fields = ("ticket_number", "customer_name", "customer_phone", "subject")
    readonly_fields = ("uid", "ticket_number", "created_at", "updated_at")
    inlines = [ComplaintNoteInline]


@admin.register(ComplaintNote)
class ComplaintNoteAdmin(admin.ModelAdmin):
    list_display = ("complaint", "author", "created_at")
    readonly_fields = ("created_at",)
