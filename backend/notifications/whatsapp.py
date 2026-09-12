"""Credential-free SO introduction previews. No network calls or live sender."""

import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from accounts.models import User
from leads.models import Lead, LeadAudit
from leads.outcomes import CLOSED_STATUSES
from .models import WhatsAppContact, WhatsAppMessage


def whatsapp_mode():
    mode = settings.WHATSAPP_MODE
    if mode not in {"preview", "disabled"}:
        raise ImproperlyConfigured("WHATSAPP_MODE must be preview or disabled. Live sending requires a provider integration.")
    return mode


def normalize_phone(value):
    """Local CRM numbers are Indian; explicit international numbers retain their prefix."""
    compact = re.sub(r"[\s().-]", "", value or "")
    if re.fullmatch(r"[0-9]{10}", compact):
        return "+91" + compact
    if re.fullmatch(r"91[0-9]{10}", compact):
        return "+" + compact
    if re.fullmatch(r"\+[1-9][0-9]{7,14}", compact):
        return compact
    return ""


def cancel_previews(lead, reason):
    # Preview records are never eligible for future live delivery.
    lead.whatsapp_messages.filter(status=WhatsAppMessage.Status.PREVIEW).update(
        status=WhatsAppMessage.Status.CANCELLED, reason=reason, updated_at=timezone.now(),
    )


def may_record_agreement(user, lead):
    return bool(user and user.is_active and not user.deleted_at and (
        user.is_admin or (user.role == User.Role.CRE and lead.assigned_so_id == user.pk)
    ))


def save_agreement(lead, agreed, actor, *, reason=""):
    """Caller holds the lead lock; use None as actor only for automatic invalidation."""
    if actor and not may_record_agreement(actor, lead):
        raise PermissionDenied("Only the assigned CE or an administrator can record WhatsApp agreement.")
    contact, _ = WhatsAppContact.objects.get_or_create(lead=lead)
    phone = normalize_phone(lead.phone)
    if contact.agreed == agreed and contact.phone == phone and contact.recorded_at:
        return contact
    before = {"agreed": contact.agreed, "phone": contact.phone}
    contact.agreed = agreed
    contact.phone = phone
    contact.recorded_by = actor
    contact.recorded_at = timezone.now()
    contact.save(update_fields=["agreed", "phone", "recorded_by", "recorded_at"])
    LeadAudit.objects.create(lead=lead, actor=actor, event="whatsapp_agreement", before=before,
        after={"agreed": agreed, "phone": phone, "reason": reason})
    if not agreed:
        cancel_previews(lead, reason or "Customer agreement withdrawn.")
    elif before["phone"] and before["phone"] != phone:
        cancel_previews(lead, "Customer phone number changed; previous previews cancelled.")
    return contact


def skip_reason(lead, contact):
    if lead.deleted_at or lead.status in CLOSED_STATUSES:
        return "Lead is closed or deleted."
    if not contact.agreed or contact.phone != normalize_phone(lead.phone):
        return "Customer agreement not recorded for this phone number."
    if not normalize_phone(lead.phone):
        return "Customer phone number is invalid."
    so = lead.assigned_ps
    if not so or not so.is_active or so.deleted_at or so.role != User.Role.SALES_OFFICER:
        return "No active Sales Officer assigned."
    if not so.get_full_name().strip() or not normalize_phone(so.phone):
        return "Sales Officer needs a full name and valid contact number."
    if whatsapp_mode() == "disabled":
        return "WhatsApp automation is disabled."
    return ""


@transaction.atomic
def record_lead_audit(audit):
    # Both single saves and bulk assignment audits enter here. Never enroll imports.
    if audit.event == "whatsapp_agreement" or not (
        {"status", "phone", "assigned_ps"}.intersection(audit.before.keys() | audit.after.keys())
        or audit.event == "deleted"
    ):
        return
    lead = Lead.objects.select_for_update().get(pk=audit.lead_id)
    enrolling = (
        audit.event in {"so_updated", "status_changed"}
        and audit.actor and audit.actor.role == User.Role.CRE
        and audit.before.get("status") != Lead.Status.QUALIFIED
        and audit.after.get("status") == Lead.Status.QUALIFIED
        and not lead.generated_by_id and lead.source != Lead.Source.WALKIN
    )
    contact = WhatsAppContact.objects.filter(lead=lead).first()
    if not contact and not enrolling:
        return
    if not contact:
        contact = WhatsAppContact.objects.create(lead=lead)
    if contact.phone != normalize_phone(lead.phone) and contact.recorded_at:
        contact = save_agreement(lead, False, None, reason="Customer phone number changed; fresh agreement required.")
    if lead.deleted_at or lead.status in CLOSED_STATUSES or not lead.assigned_ps_id:
        cancel_previews(lead, "Lead closed, deleted, or awaiting a Sales Officer.")
    if enrolling and not contact.enrolled_at:
        contact.enrolled_at = timezone.now()
        contact.save(update_fields=["enrolled_at"])
    if not contact.enrolled_at or lead.deleted_at or lead.status in CLOSED_STATUSES or not lead.assigned_ps_id:
        return
    if contact.last_so_id == lead.assigned_ps_id or WhatsAppMessage.objects.filter(source_audit=audit).exists():
        return
    kind = WhatsAppMessage.Kind.REASSIGNMENT if contact.last_so_id else WhatsAppMessage.Kind.INTRODUCTION
    cancel_previews(lead, "Superseded by a newer Sales Officer assignment.")
    so = lead.assigned_ps
    variables = {"customer_name": lead.name, "business_name": settings.WHATSAPP_BUSINESS_NAME,
        "so_name": so.get_full_name().strip(), "so_phone": normalize_phone(so.phone)}
    reason = skip_reason(lead, contact)
    body = (
        "Hello {customer_name}, thank you for speaking with our team at {business_name}. "
        "Your Sales Officer, {so_name}, will contact you regarding your enquiry. You can reach them on {so_phone}."
        if kind == WhatsAppMessage.Kind.INTRODUCTION else
        "Hello {customer_name}, your Sales Officer for your enquiry with {business_name} has changed. "
        "Your new contact is {so_name}, reachable on {so_phone}."
    ).format(**variables)
    WhatsAppMessage.objects.get_or_create(source_audit=audit, defaults={
        "lead": lead, "so": so, "kind": kind, "mode": whatsapp_mode(), "recipient": normalize_phone(lead.phone),
        "template": settings.WHATSAPP_TEMPLATE_INTRODUCTION if kind == WhatsAppMessage.Kind.INTRODUCTION else settings.WHATSAPP_TEMPLATE_REASSIGNMENT,
        "language": settings.WHATSAPP_LANGUAGE, "variables": variables, "body": body,
        "status": WhatsAppMessage.Status.SKIPPED if reason else WhatsAppMessage.Status.PREVIEW, "reason": reason,
    })
    contact.last_so = so
    contact.save(update_fields=["last_so"])


def send_whatsapp_message(message):
    """Provider integration entry point. Historical previews must never be sent."""
    raise ImproperlyConfigured("Live WhatsApp delivery is not implemented. Preview records cannot be sent.")
