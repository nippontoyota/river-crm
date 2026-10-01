"""Current outcome classification shared by CEO totals, lists and exports."""
from collections import Counter

from django.db.models import Case, CharField, Count, F, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Trim

from accounts.models import User
from leads.models import CallLog
from .models import OperationEvent


STAGE_LABELS = {
    "FRESH": "Fresh", "RNR": "RNR", "SWITCHED_OFF": "Switch Off",
    "CALLBACK": "Call Me Back", "PENDING": "Pending", "QUALIFIED": "Qualified",
    "UNQUALIFIED": "Unqualified", "WALKIN": "Booking Done", "WON": "Retail Done",
    "LOST": "Lost Lead",
}
UNKNOWN_REASON = "Reason not recorded"


def classified_leads(queryset):
    latest = CallLog.objects.filter(lead_id=OuterRef("pk")).order_by("-created_at", "-id")
    reopened = OperationEvent.objects.filter(lead_id=OuterRef("pk"), kind="reopened").order_by("-occurred_at", "-id")
    queryset = queryset.annotate(
        _analysis_call_at=Subquery(latest.values("created_at")[:1]),
        _analysis_call_status=Subquery(latest.values("status")[:1]),
        _analysis_outcome=Trim(Subquery(latest.values("outcome")[:1])),
        _analysis_reopened_at=Subquery(reopened.values("occurred_at")[:1]),
    )
    lost = Q(status="LOST") | Q(sales_outcome="LOST")
    usable = (Q(_analysis_reopened_at__isnull=True) | Q(_analysis_call_at__gt=F("_analysis_reopened_at"))) & ~Q(_analysis_outcome="")
    compatible = Q(_analysis_call_status=F("status"))
    fallback = Case(*[When(status=key, then=Value(value)) for key, value in STAGE_LABELS.items()], default=Value("Not recorded"), output_field=CharField())
    outcome_label = Case(*[When(_analysis_outcome=key, then=Value(value)) for key, value in STAGE_LABELS.items()], default=F("_analysis_outcome"), output_field=CharField())
    recorded_reason = ~Q(_analysis_outcome__in=["LOST", "Lost", "Lost Lead"])
    return queryset.annotate(
        analysis_status=Case(
            When(lost, then=Value("Lost Lead")),
            When(Q(status="WON") | Q(sales_outcome="RETAILED"), then=Value("Retail Done")),
            When(status="UNQUALIFIED", then=Value("Unqualified")),
            When(usable & compatible, then=outcome_label),
            default=fallback, output_field=CharField(),
        ),
        loss_reason=Case(
            When(lost & usable & recorded_reason & Q(_analysis_call_status="LOST"), then=F("_analysis_outcome")),
            When(lost, then=Value(UNKNOWN_REASON)),
            default=Value(""), output_field=CharField(),
        ),
    )


def filter_analysis(queryset, params):
    queryset = classified_leads(queryset)
    for key in ("analysis_status", "loss_reason"):
        if params.get(key):
            queryset = queryset.filter(**{key: params[key]})
    officer = params.get("analysis_officer")
    if officer:
        queryset = queryset.filter(assigned_ps_id=None if officer == "__unassigned__" else int(officer))
    return queryset


def lead_analysis(filters):
    queryset = filter_analysis(filters.period(filters.base_leads(), "enquiry_date"), filters.params)
    # Roll up database groups, never individual leads or per-officer queries.
    groups = queryset.order_by().values("assigned_ps_id", "analysis_status", "loss_reason").annotate(count=Count("pk", distinct=True))
    statuses, reasons, officers = Counter(), Counter(), {}
    for row in groups:
        status, count = row["analysis_status"], row["count"]
        statuses[status] += count
        if status == "Lost Lead":
            reasons[row["loss_reason"]] += count
        officers.setdefault(row["assigned_ps_id"], Counter())[status] += count
    users = User.objects.in_bulk([pk for pk in officers if pk is not None])
    officer_rows = []
    for pk, counts in officers.items():
        user = users.get(pk)
        officer_rows.append({
            "key": str(pk) if pk is not None else "__unassigned__",
            "name": user.history_display_name if user else "Unassigned Sales Officer",
            "branch": user.location if user else "", "total": sum(counts.values()),
            "statuses": dict(counts),
        })
    def rows(counts):
        return [{"key": key, "label": key, "count": count} for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    return {
        "total": sum(statuses.values()), "lost_total": sum(reasons.values()),
        "statuses": rows(statuses), "loss_reasons": rows(reasons),
        "officers": sorted(officer_rows, key=lambda row: (-row["total"], row["name"], row["key"])),
    }
