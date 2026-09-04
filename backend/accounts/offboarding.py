import hashlib
import json
from collections import Counter
from uuid import uuid4

from django.core.cache import caches
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from complaints.models import Complaint, ComplaintNote
from leads.models import FollowUp, Lead, LeadAudit
from notifications.models import Notification

from .models import User, UserLifecycleEvent


CLOSED_LEAD_STATUSES = {Lead.Status.WON, Lead.Status.LOST, Lead.Status.UNQUALIFIED}
OPEN_COMPLAINT_STATUSES = {Complaint.Status.OPEN, Complaint.Status.IN_PROGRESS, Complaint.Status.ESCALATED}


class OffboardingConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "offboarding_conflict"


def _role_fields(user):
    if user.role == User.Role.CRE:
        return "assigned_so", "needs_cre_reassignment", "CRE", "assigned_leads"
    if user.role == User.Role.SALES_OFFICER:
        return "assigned_ps", "needs_so_reassignment", "SO", "ps_leads"
    raise ValidationError({"detail": "Only CRE and PS/SO accounts can use this workflow."})


def _snapshot_version(user, leads, followups, complaints):
    payload = {
        "user": [user.id, user.is_active, str(user.deleted_at or "")],
        "leads": [[lead.id, lead.status, lead.assigned_so_id, lead.assigned_ps_id, str(lead.updated_at)] for lead in sorted(leads, key=lambda item: item.id)],
        "followups": [[item.id, item.lead_id, item.so_id, str(item.scheduled_for), str(item.resolved_at or ""), item.reminder_held] for item in sorted(followups, key=lambda followup: followup.id)],
        "complaints": [[item.id, item.status, item.assigned_to_id, str(item.updated_at)] for item in sorted(complaints, key=lambda complaint: complaint.id)],
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _work_for(user, lock=False):
    owner_field, _, _, _ = _role_fields(user)
    followup_lead_ids = FollowUp.objects.filter(
        so=user,
        resolved_at__isnull=True,
        lead__deleted_at__isnull=True,
    ).values("lead_id")
    lead_query = Q(**{owner_field: user}) | Q(id__in=followup_lead_ids)
    leads = Lead.objects.filter(deleted_at__isnull=True).filter(lead_query)
    if lock:
        leads = leads.select_for_update()
    else:
        leads = leads.select_related("assigned_so", "assigned_ps")
    leads = list(leads)
    followups = FollowUp.objects.filter(
        so=user,
        resolved_at__isnull=True,
        lead__deleted_at__isnull=True,
    )
    complaints = Complaint.objects.filter(assigned_to=user, status__in=OPEN_COMPLAINT_STATUSES)
    if lock:
        followups = followups.select_for_update()
        complaints = complaints.select_for_update()
    else:
        followups = followups.select_related("lead", "lead__assigned_so", "lead__assigned_ps")
    return leads, list(followups), list(complaints)


def offboarding_impact(user):
    owner_field, _, assignment_role, relation = _role_fields(user)
    leads, followups, complaints = _work_for(user)
    owned = [lead for lead in leads if getattr(lead, f"{owner_field}_id") == user.id]
    actionable = [lead for lead in owned if lead.status not in CLOSED_LEAD_STATUSES]
    status_labels = dict(Lead.Status.choices)
    groups = []
    for lead_status in sorted({lead.status for lead in actionable}):
        grouped = [lead for lead in actionable if lead.status == lead_status]
        groups.append({
            "status": lead_status,
            "label": status_labels.get(lead_status, lead_status),
            "count": len(grouped),
            "branches": sorted({lead.branch.strip() or "No branch" for lead in grouped}),
        })
    users = User.objects.filter(role=user.role, is_active=True, deleted_at__isnull=True).exclude(pk=user.pk)
    active_filter = Q(**{f"{relation}__deleted_at__isnull": True}) & ~Q(**{f"{relation}__status__in": CLOSED_LEAD_STATUSES})
    eligible = [{
        "id": candidate.id,
        "name": candidate.get_full_name() or candidate.email,
        "location": candidate.location,
        "load": candidate.load,
    } for candidate in users.annotate(load=Count(relation, filter=active_filter, distinct=True)).order_by("first_name", "last_name", "id")]
    return {
        "version": _snapshot_version(user, leads, followups, complaints),
        "assignment_role": assignment_role,
        "lead_groups": groups,
        "actionable_count": len(actionable),
        "closed_count": len(owned) - len(actionable),
        "followup_count": len(followups),
        "complaint_count": len(complaints),
        "eligible_users": eligible,
    }


def _clear_analytics_cache():
    try:
        caches["analytics"].clear()
    except Exception:
        pass


def _invalidate_user(user):
    Notification.objects.filter(user=user).delete()
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


@transaction.atomic
def offboard_user(user_id, actor, action, impact_version, routes, reason=""):
    if not isinstance(routes, list):
        raise ValidationError({"routes": "Expected a list of status routes."})
    if any(not isinstance(route, dict) or not isinstance(route.get("recipient_ids", []), list) for route in routes):
        raise ValidationError({"routes": "Each status route needs a recipient list."})
    reason = reason.strip() if isinstance(reason, str) else ""
    if len(reason) > 500:
        raise ValidationError({"reason": "Use 500 characters or fewer."})
    requested_recipient_ids = {
        int(recipient_id)
        for route in routes if isinstance(route, dict)
        for recipient_id in route.get("recipient_ids", [])
        if str(recipient_id).isdigit()
    }
    locked_users = {item.id: item for item in User.objects.select_for_update().filter(id__in={user_id, *requested_recipient_ids}).order_by("id")}
    user = locked_users.get(user_id)
    if not user or user.deleted_at:
        raise ValidationError({"detail": "This account no longer exists."})
    owner_field, queue_field, assignment_role, relation = _role_fields(user)
    if action == UserLifecycleEvent.Action.DISABLED and not user.is_active:
        raise ValidationError({"detail": "This account is already disabled."})
    if action == UserLifecycleEvent.Action.DELETED and not reason:
        raise ValidationError({"reason": "A deletion reason is required."})

    leads, followups, complaints = _work_for(user, lock=True)
    if _snapshot_version(user, leads, followups, complaints) != impact_version:
        raise OffboardingConflict({"detail": "Work changed after the preview opened. Review the refreshed counts and try again."})

    owned = [lead for lead in leads if getattr(lead, f"{owner_field}_id") == user.id]
    actionable = [lead for lead in owned if lead.status not in CLOSED_LEAD_STATUSES]
    routes_by_status = {route.get("status"): route for route in routes if isinstance(route, dict)}
    missing = sorted({lead.status for lead in actionable} - set(routes_by_status))
    if missing:
        raise ValidationError({"routes": f"Choose a destination for: {', '.join(missing)}."})

    recipients = {key: value for key, value in locked_users.items() if key in requested_recipient_ids}
    invalid_recipients = requested_recipient_ids - set(recipients)
    invalid_recipients |= {
        candidate.id
        for candidate in recipients.values()
        if candidate.id == user.id or not candidate.is_active or candidate.deleted_at or candidate.role != user.role
    }
    if invalid_recipients:
        raise OffboardingConflict({"detail": "A selected replacement is no longer eligible. Refresh the preview and choose again."})

    active_filter = Q(**{f"{relation}__deleted_at__isnull": True}) & ~Q(**{f"{relation}__status__in": CLOSED_LEAD_STATUSES})
    loads = {candidate.id: candidate.load for candidate in User.objects.filter(id__in=recipients).annotate(load=Count(relation, filter=active_filter, distinct=True))}
    new_owners = {}
    distribution = Counter()
    audits = []
    now = timezone.now()
    owner_id_field = f"{owner_field}_id"
    for lead in sorted(actionable, key=lambda item: (item.status, item.created_at, item.id)):
        route = routes_by_status[lead.status]
        destination = route.get("destination")
        selected = [recipients[int(value)] for value in route.get("recipient_ids", []) if str(value).isdigit() and int(value) in recipients]
        if destination not in {"POOL", "DISTRIBUTE"}:
            raise ValidationError({"routes": f"Choose Pool or Distribute for {lead.status}."})
        if destination == "DISTRIBUTE" and not selected:
            raise ValidationError({"routes": f"Choose at least one replacement for {lead.status}."})
        eligible = selected
        if assignment_role == "SO":
            eligible = [candidate for candidate in selected if lead.branch.strip() and candidate.location.strip().casefold() == lead.branch.strip().casefold()]
        replacement = min(eligible, key=lambda candidate: (loads.get(candidate.id, 0), candidate.id)) if destination == "DISTRIBUTE" and eligible else None
        before = getattr(lead, owner_id_field)
        setattr(lead, owner_field, replacement)
        setattr(lead, queue_field, replacement is None)
        lead.updated_at = now
        new_owners[lead.id] = replacement
        if replacement:
            loads[replacement.id] = loads.get(replacement.id, 0) + 1
            distribution[replacement.id] += 1
        audits.append(LeadAudit(
            lead=lead,
            actor=actor,
            event="offboarding_reassigned" if replacement else "offboarding_pooled",
            before={owner_field: before},
            after={owner_field: replacement.id if replacement else None, queue_field: replacement is None, "account_action": action},
        ))

    changed_leads = list(actionable)
    leads_by_id = {lead.id: lead for lead in leads}
    for followup in followups:
        lead = leads_by_id[followup.lead_id]
        replacement = new_owners.get(lead.id)
        if lead.id in new_owners:
            if replacement:
                followup.so = replacement
        elif followup.so_id == user.id and lead.status not in CLOSED_LEAD_STATUSES:
            current_owner = getattr(lead, owner_field)
            if current_owner and current_owner.is_active and not current_owner.deleted_at:
                followup.so = current_owner
            else:
                before = getattr(lead, owner_id_field)
                setattr(lead, owner_field, None)
                setattr(lead, queue_field, True)
                lead.updated_at = now
                if lead not in changed_leads:
                    changed_leads.append(lead)
                    audits.append(LeadAudit(lead=lead, actor=actor, event="offboarding_followup_pooled", before={owner_field: before}, after={owner_field: None, queue_field: True}))
        followup.reminder_held = True

    if changed_leads:
        Lead.objects.bulk_update(changed_leads, [owner_field, queue_field, "updated_at"], batch_size=1000)
    if audits:
        LeadAudit.objects.bulk_create(audits, batch_size=1000)
    if followups:
        FollowUp.objects.bulk_update(followups, ["so", "reminder_held"], batch_size=1000)
    if complaints:
        ComplaintNote.objects.bulk_create([
            ComplaintNote(complaint=complaint, author=actor, content=f"Returned to the complaint pool when {user.get_full_name() or user.email} was {action.lower()}.")
            for complaint in complaints
        ])
        for complaint in complaints:
            complaint.assigned_to = None
            complaint.updated_at = now
        Complaint.objects.bulk_update(complaints, ["assigned_to", "updated_at"], batch_size=1000)

    Notification.objects.bulk_create([
        Notification(user_id=recipient_id, kind=Notification.Kind.ASSIGNMENT, message=f"You have {count} reassigned lead(s).")
        for recipient_id, count in distribution.items()
    ])
    _invalidate_user(user)
    user.is_active = False
    update_fields = ["is_active"]
    if action == UserLifecycleEvent.Action.DELETED:
        user.email = f"deleted-{user.id}-{uuid4().hex}@invalid.local"
        user.phone = ""
        user.is_staff = False
        user.is_superuser = False
        user.deleted_at = now
        user.set_unusable_password()
        user.groups.clear()
        user.user_permissions.clear()
        update_fields += ["email", "phone", "is_staff", "is_superuser", "deleted_at", "password"]
    user.save(update_fields=update_fields)
    summary = {
        "actionable_leads": len(actionable),
        "closed_leads_retained": len(owned) - len(actionable),
        "followups_held": len(followups),
        "complaints_pooled": len(complaints),
        "distribution": dict(distribution),
        "pooled_leads": sum(1 for replacement in new_owners.values() if replacement is None),
    }
    UserLifecycleEvent.objects.create(user=user, actor=actor, action=action, reason=reason, summary=summary)
    transaction.on_commit(_clear_analytics_cache)
    return summary


@transaction.atomic
def enable_user(user_id, actor):
    user = User.objects.select_for_update().filter(pk=user_id).first()
    if not user or user.deleted_at:
        raise ValidationError({"detail": "Deleted accounts cannot be enabled."})
    owner_field, _, _, _ = _role_fields(user)
    if user.is_active:
        raise ValidationError({"detail": "This account is already active."})
    if Lead.objects.filter(deleted_at__isnull=True, **{owner_field: user}).exclude(status__in=CLOSED_LEAD_STATUSES).exists():
        raise OffboardingConflict({"detail": "This disabled account still owns actionable leads. Move them to the reassignment queue first."})
    user.is_active = True
    user.save(update_fields=["is_active"])
    UserLifecycleEvent.objects.create(user=user, actor=actor, action=UserLifecycleEvent.Action.ENABLED)
    transaction.on_commit(_clear_analytics_cache)
    return user
