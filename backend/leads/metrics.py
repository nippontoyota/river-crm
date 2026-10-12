from django.db.models import Count, Exists, OuterRef, Q

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
