from django.db.models import Avg, CharField, Count, F, Q, Value
from django.db.models.functions import Cast, Concat, Lower, Trim
from django.utils import timezone
from rest_framework import serializers

from ceo.filters import ReportFilters
from leads.models import Lead
from .models import FeedbackAttempt, FeedbackTask
from .permissions import visible_tasks
from .services import branch_key


def filters_for(params):
    # Reuse the CEO date vocabulary without applying sales-specific filters to feedback.
    dates = params.copy()
    for key in list(dates):
        if key not in {"range", "date_from", "date_to"}:
            dates.pop(key)
    if not dates.get("range"):
        dates["range"] = "all"
    return ReportFilters(dates)


def filter_scope(queryset, params, caller_field="assigned_to_id", branch_field="branch"):
    branches = ["" if value == "__unknown__" else branch_key(value) for value in params.getlist("branch") if value]
    if branches:
        queryset = queryset.filter(**{f"{branch_field}__in": branches})
    if caller := params.get("caller"):
        if caller == "unassigned" and caller_field == "assigned_to_id":
            queryset = queryset.filter(assigned_to__isnull=True)
        elif str(caller).isdigit() and int(caller) > 0:
            queryset = queryset.filter(**{caller_field: int(caller)})
        elif caller == "unassigned":
            queryset = queryset.none()
        else:
            raise serializers.ValidationError({"caller": "Choose a feedback caller."})
    return queryset


def buckets():
    now, today = timezone.now(), timezone.localdate()
    return {
        "open": Q(status="OPEN"),
        "cancelled": Q(status="CANCELLED"),
        "issues": Q(issue__status__in=["OPEN", "ACKNOWLEDGED"]),
        "upcoming": Q(status="OPEN", next_call_at__gt=now),
        "due": Q(status="OPEN", next_call_at__lte=now, next_call_at__date=today),
        "overdue": Q(status="OPEN", next_call_at__date__lt=today),
        "completed": Q(status="COMPLETED"), "unreachable": Q(status="UNREACHABLE"),
        "declined": Q(status="DECLINED"), "invalid_number": Q(status="INVALID_NUMBER"),
        "unassigned": Q(status="OPEN", assigned_to__isnull=True),
    }


def counts(queryset):
    result = queryset.aggregate(total=Count("id"), leads=Count("lead_id", distinct=True),
        on_time=Count("id", filter=Q(on_time=True) & ~Q(origin="HISTORICAL")),
        historical=Count("id", filter=Q(origin="HISTORICAL")),
        rated=Count("satisfaction"), average_satisfaction=Avg("satisfaction"), **{key: Count("id", filter=condition) for key, condition in buckets().items()})
    result["completion_rate"] = round(100 * result["completed"] / result["total"], 1) if result["total"] else 0
    return result


def task_query(user, params, period=True, row_filters=True):
    queryset = filter_scope(visible_tasks(user), params)
    if period:
        queryset = filters_for(params).period(queryset, "original_due_at__date")
    if row_filters:
        if kind := params.get("kind"):
            if kind not in FeedbackTask.Kind.values:
                raise serializers.ValidationError({"kind": "Choose TDF, PBF, PSF, SVC or GEN."})
            queryset = queryset.filter(kind=kind)
        if bucket := params.get("bucket"):
            if bucket not in buckets():
                raise serializers.ValidationError({"bucket": "Choose a valid task status."})
            queryset = queryset.filter(buckets()[bucket])
        if query := params.get("q"):
            queryset = queryset.filter(Q(lead__name__icontains=query) | Q(lead__phone__icontains=query) | Q(service_event__request__customer_snapshot__customer_name__icontains=query) | Q(service_event__request__customer_snapshot__customer_phone__icontains=query))
    if origin := params.get("origin"):
        if origin not in FeedbackTask.Origin.values:
            raise serializers.ValidationError({"origin": "Choose a valid task origin."})
        queryset = queryset.filter(origin=origin)
    return queryset


def customer_count(tasks):
    from django.db.models import Case, When
    return tasks.annotate(customer_key=Case(
        When(lead_id__isnull=False, then=Concat(Value("lead:"), Cast("lead_id", CharField()))),
        When(service_event__request__vehicle__related_lead_id__isnull=False, then=Concat(Value("lead:"), Cast("service_event__request__vehicle__related_lead_id", CharField()))),
        default=Concat(Value("vehicle:"), Cast("service_event__request__vehicle_id", CharField())), output_field=CharField()
    )).values("customer_key").distinct().count()


def report(user, params):
    cohort = task_query(user, params, row_filters=False)
    backlog = task_query(user, params, period=False, row_filters=False)
    period = filters_for(params)
    attempts = FeedbackAttempt.objects.filter(task__lead__deleted_at__isnull=True)
    if user.role == "FEEDBACK":
        attempts = attempts.filter(caller=user, task__in=visible_tasks(user))
    elif user.role == "SALES_MANAGER":
        attempts = attempts.filter(branch=branch_key(user.location)) if branch_key(user.location) else attempts.none()
    if origin := params.get("origin"):
        attempts = attempts.filter(task__origin=origin)
    attempts = period.period(filter_scope(attempts, params, caller_field="caller_id"), "created_at__date")
    leads = Lead.objects.filter(deleted_at__isnull=True).annotate(key=Lower(Trim("branch")))
    if user.role == "SALES_MANAGER":
        leads = leads.filter(key=branch_key(user.location)) if branch_key(user.location) else leads.none()
    branches = ["" if b == "__unknown__" else branch_key(b) for b in params.getlist("branch") if b]
    if branches:
        leads = leads.filter(key__in=branches)
    all_tasks = visible_tasks(user).filter(lead__in=leads, kind__in=["TDF", "PBF", "PSF"]).exclude(origin="HISTORICAL")
    comparisons = []
    if user.role != "FEEDBACK":
        comparisons = list(cohort.values("branch", "assigned_to_id", "assigned_to__first_name", "assigned_to__last_name", "assigned_to__email").annotate(
            total=Count("id"), completed=Count("id", filter=Q(status="COMPLETED")), overdue=Count("id", filter=buckets()["overdue"]),
            unreachable=Count("id", filter=Q(status="UNREACHABLE")), unresolved_issues=Count("id", filter=buckets()["issues"]), average_satisfaction=Avg("satisfaction"), historical=Count("id", filter=Q(origin="HISTORICAL"))).order_by("branch", "assigned_to_id"))
    return {"summary": counts(cohort), "types": [{"kind": kind, **counts(cohort.filter(kind=kind))} for kind in FeedbackTask.Kind.values],
        "backlog": counts(backlog.filter(status="OPEN")), "unresolved_issues": backlog.filter(buckets()["issues"]).count(), "activity": {"attempts": attempts.count(), "customers": customer_count(FeedbackTask.objects.filter(pk__in=attempts.values("task_id")))},
        "coverage": {"leads_with_feedback": all_tasks.values("lead_id").distinct().count(), "all_leads": leads.count()},
        "satisfaction": [{"rating": rating, "count": cohort.filter(satisfaction=rating).count()} for rating in [1, 2, 3, 4, 5]],
        "origins": {origin: counts(cohort.filter(origin=origin)) for origin in FeedbackTask.Origin.values},
        "customers": customer_count(cohort), "comparisons": comparisons, "date_basis": "Original due date", "date_from": period.start, "date_to": period.end, "generated_at": timezone.now()}
