from django.db.models import Count, Exists, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from .models import CallLog, FollowUp, Lead, LeadAudit


def actionable_followups():
    """Outstanding outbound work for a lead's current, active owner."""
    return FollowUp.objects.filter(
        resolved_at__isnull=True, origin="OUTBOUND", reminder_held=False,
        lead__deleted_at__isnull=True, so__is_active=True, so__deleted_at__isnull=True,
    ).exclude(lead__status__in=[Lead.Status.WON, Lead.Status.LOST, Lead.Status.UNQUALIFIED]).filter(
        Q(so__role="SO", so_id=F("lead__assigned_ps_id"))
        | Q(so__role="CRE", so_id=F("lead__assigned_so_id"))
    )


def etbr_aggregates():
    """Progress of distinct enquiries in the caller's authorized date cohort."""
    return {
        "etbr_enquired": Count("id", distinct=True),
        "etbr_test_drive_completed": Count("id", filter=Q(test_drive_completed_at__isnull=False), distinct=True),
        "etbr_booked": Count("id", filter=Q(sales_outcome__in=[Lead.SalesOutcome.BOOKED, Lead.SalesOutcome.RETAILED]), distinct=True),
        "etbr_retailed": Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.RETAILED), distinct=True),
    }


PS_HANDLING_FILTERS = {
    "passed": Q(assigned_ps__isnull=False),
    "untouched": Q(assigned_ps__isnull=False, _ps_touched=False),
}
CE_HANDLING_FILTERS = {
    "passed": Q(assigned_so__isnull=False),
    "untouched": Q(assigned_so__isnull=False, _ce_touched=False),
}


def with_owner_handling(queryset, owner_field, prefix):
    """Only the current owner's activity since their latest allocation counts."""
    allocation = LeadAudit.objects.filter(
        lead_id=OuterRef("pk"), after__has_key=owner_field,
        event__in=["assigned_ps", "assigned_cre", "bucket_assigned_cre", "auto_assigned_cre", "reassignment_completed", "offboarding_reassigned"],
    ).order_by("-created_at", "-pk")
    allocated_at = f"_{prefix}_allocated_at"
    queryset = queryset.annotate(**{allocated_at: Coalesce(Subquery(allocation.values("created_at")[:1]), F("created_at"))})
    calls = CallLog.objects.filter(
        lead_id=OuterRef("pk"), so_id=OuterRef(owner_field + "_id"), created_at__gte=OuterRef(allocated_at),
    )
    actions = LeadAudit.objects.filter(
        lead_id=OuterRef("pk"), actor_id=OuterRef(owner_field + "_id"), created_at__gte=OuterRef(allocated_at),
        event__in=["created", "so_updated", "status_changed", "test_drive_completed", "qualification_updated", "details_updated"],
    )
    return queryset.annotate(**{f"_{prefix}_called": Exists(calls), f"_{prefix}_touched": Exists(calls) | Exists(actions)})


def with_ps_handling(queryset):
    return with_owner_handling(queryset, "assigned_ps", "ps")


def with_ce_handling(queryset):
    return with_owner_handling(queryset, "assigned_so", "ce")


def ps_handling_counts():
    return {
        "passed_to_ps": Count("pk", filter=PS_HANDLING_FILTERS["passed"], distinct=True),
        "untouched_by_ps": Count("pk", filter=PS_HANDLING_FILTERS["untouched"], distinct=True),
    }


def lost_reason_groups(queryset):
    """Count each closed lost lead under its latest recorded loss reason."""
    lost_statuses = (Lead.Status.LOST, Lead.Status.UNQUALIFIED)
    loss_call = CallLog.objects.filter(lead_id=OuterRef("pk"), status__in=lost_statuses).order_by("-created_at", "-pk")
    leads = queryset.filter(status__in=lost_statuses).annotate(
        loss_outcome=Subquery(loss_call.values("outcome")[:1]),
        loss_remarks=Subquery(loss_call.values("remarks")[:1]),
    ).values_list("pk", "status", "loss_outcome", "loss_remarks")
    groups = {}
    for lead_id, status, outcome, remarks in leads:
        first_line = (remarks or "").splitlines()[0].strip() if remarks else ""
        recorded = first_line.split(":", 1)[1].strip() if first_line.casefold().startswith("lost reason:") else ""
        reason = recorded or (outcome if outcome and outcome.upper() not in {"LOST", "UNQUALIFIED"} else "")
        reason = reason[0].upper() + reason[1:] if reason else "Not interested" if status == Lead.Status.UNQUALIFIED else "Reason not recorded"
        group = groups.setdefault(reason.casefold(), {"reason": reason, "ids": []})
        group["ids"].append(lead_id)
    return sorted(groups.values(), key=lambda group: (-len(group["ids"]), group["reason"].casefold()))
