from django.db.models import Count, Q
from django.db.models.functions import Lower, Trim
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
        "upcoming": Q(status="OPEN", next_call_at__gt=now),
        "due": Q(status="OPEN", next_call_at__lte=now, next_call_at__date=today),
        "overdue": Q(status="OPEN", next_call_at__date__lt=today),
        "completed": Q(status="COMPLETED"), "unreachable": Q(status="UNREACHABLE"),
        "declined": Q(status="DECLINED"), "invalid_number": Q(status="INVALID_NUMBER"),
        "unassigned": Q(status="OPEN", assigned_to__isnull=True),
    }


def counts(queryset):
    result = queryset.aggregate(total=Count("id"), leads=Count("lead_id", distinct=True),
        on_time=Count("id", filter=Q(on_time=True)), **{key: Count("id", filter=condition) for key, condition in buckets().items()})
    result["completion_rate"] = round(100 * result["completed"] / result["total"], 1) if result["total"] else 0
    return result


def task_query(user, params, period=True, row_filters=True):
    queryset = filter_scope(visible_tasks(user), params)
    if period:
        queryset = filters_for(params).period(queryset, "original_due_at__date")
    if row_filters:
        if kind := params.get("kind"):
            if kind not in FeedbackTask.Kind.values:
                raise serializers.ValidationError({"kind": "Choose TDF, PBF or PSF."})
            queryset = queryset.filter(kind=kind)
        if bucket := params.get("bucket"):
            if bucket not in buckets():
                raise serializers.ValidationError({"bucket": "Choose a valid task status."})
            queryset = queryset.filter(buckets()[bucket])
        if query := params.get("q"):
            queryset = queryset.filter(Q(lead__name__icontains=query) | Q(lead__phone__icontains=query))
    return queryset


def report(user, params):
    cohort = task_query(user, params, row_filters=False)
    backlog = task_query(user, params, period=False, row_filters=False)
    period = filters_for(params)
    attempts = FeedbackAttempt.objects.filter(task__lead__deleted_at__isnull=True)
    if user.role == "FEEDBACK":
        attempts = attempts.filter(caller=user, task__in=visible_tasks(user))
    elif user.role == "SALES_MANAGER":
        attempts = attempts.filter(branch=branch_key(user.location)) if branch_key(user.location) else attempts.none()
    attempts = period.period(filter_scope(attempts, params, caller_field="caller_id"), "created_at__date")
    leads = Lead.objects.filter(deleted_at__isnull=True).annotate(key=Lower(Trim("branch")))
    if user.role in {"FEEDBACK", "SALES_MANAGER"}:
        leads = leads.filter(key=branch_key(user.location)) if branch_key(user.location) else leads.none()
    branches = ["" if b == "__unknown__" else branch_key(b) for b in params.getlist("branch") if b]
    if branches:
        leads = leads.filter(key__in=branches)
    all_tasks = visible_tasks(user).filter(lead__in=leads)
    comparisons = []
    if user.role != "FEEDBACK":
        comparisons = list(cohort.values("branch", "assigned_to_id", "assigned_to__first_name", "assigned_to__last_name", "assigned_to__email").annotate(
            total=Count("id"), completed=Count("id", filter=Q(status="COMPLETED")), overdue=Count("id", filter=buckets()["overdue"]),
            unreachable=Count("id", filter=Q(status="UNREACHABLE"))).order_by("branch", "assigned_to_id"))
    return {"summary": counts(cohort), "types": [{"kind": kind, **counts(cohort.filter(kind=kind))} for kind in FeedbackTask.Kind.values],
        "backlog": counts(backlog.filter(status="OPEN")), "activity": {"attempts": attempts.count(), "customers": attempts.values("task__lead_id").distinct().count()},
        "coverage": {"leads_with_feedback": all_tasks.values("lead_id").distinct().count(), "all_leads": leads.count()},
        "comparisons": comparisons, "date_basis": "Original due date", "date_from": period.start, "date_to": period.end, "generated_at": timezone.now()}
