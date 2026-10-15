from django.db.models import Count, Exists, OuterRef, Q, Subquery

from .models import CallLog, Lead


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
    "untouched": Q(assigned_ps__isnull=False, _ps_called=False),
}


def with_ps_handling(queryset):
    return queryset.annotate(_ps_called=Exists(
        CallLog.objects.filter(lead_id=OuterRef("pk"), so_id=OuterRef("assigned_ps_id"))
    ))


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
