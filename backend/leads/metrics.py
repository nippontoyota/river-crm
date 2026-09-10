from django.db.models import Count, Q

from .models import Lead


def etbr_aggregates():
    """Progress of distinct enquiries in the caller's authorized date cohort."""
    return {
        "etbr_enquired": Count("id", distinct=True),
        "etbr_test_drive_completed": Count("id", filter=Q(test_drive_completed_at__isnull=False), distinct=True),
        "etbr_booked": Count("id", filter=Q(sales_outcome__in=[Lead.SalesOutcome.BOOKED, Lead.SalesOutcome.RETAILED]), distinct=True),
        "etbr_retailed": Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.RETAILED), distinct=True),
    }
