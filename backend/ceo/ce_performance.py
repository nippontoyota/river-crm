"""CE workload and recorded CE activity, independent of later sales outcomes."""
from django.db.models import Case, CharField, Count, F, Max, OuterRef, Q, Subquery, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Lower, Trim
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User
from leads.metrics import actionable_followups, with_ce_handling
from leads.models import CallLog, Lead, LeadAudit


def ce_lead_outcomes(leads):
    """A single, exclusive result for each current CE allocation."""
    leads = with_ce_handling(leads)
    calls = CallLog.objects.filter(
        lead_id=OuterRef("pk"), so_id=OuterRef("assigned_so_id"), created_at__gte=OuterRef("_ce_allocated_at"),
    ).order_by("-created_at", "-pk")
    changes = LeadAudit.objects.filter(
        lead_id=OuterRef("pk"), actor_id=OuterRef("assigned_so_id"), created_at__gte=OuterRef("_ce_allocated_at"),
        event__in=["status_changed", "so_updated"], after__status__in=Lead.Status.values,
    ).filter(Q(before__status__isnull=True) | ~Q(before__status=F("after__status"))).order_by("-created_at", "-pk")
    leads = leads.annotate(
        _ce_call_status=Subquery(calls.values("status")[:1]),
        _ce_call_at=Subquery(calls.values("created_at")[:1]),
        _ce_change_status=Subquery(changes.annotate(value=KeyTextTransform("status", "after")).values("value")[:1]),
        _ce_change_at=Subquery(changes.values("created_at")[:1]),
    ).annotate(_ce_status=Case(
        When(Q(_ce_change_at__isnull=False) & (Q(_ce_call_at__isnull=True) | Q(_ce_change_at__gte=F("_ce_call_at"))), then=F("_ce_change_status")),
        default=F("_ce_call_status"), output_field=CharField(),
    ))
    return leads.annotate(ce_result=Case(
        When(_ce_status="QUALIFIED", then=Value("qualified")),
        When(_ce_status__in=["LOST", "UNQUALIFIED"], then=Value("lost")),
        When(_ce_touched=False, then=Value("untouched")),
        default=Value("in_progress"), output_field=CharField(),
    ))


def ce_cohort(filters):
    users = User.objects.for_reporting().filter(role=User.Role.CRE)
    if filters.employee:
        users = users.filter(pk=filters.employee.pk)
    return ce_lead_outcomes(filters.period(filters.base_leads(employee=False), "enquiry_date")).filter(
        assigned_so_id__in=users.values("pk"),
    )


def ce_buckets(now):
    """Shared predicates keep the displayed counts and matching leads identical."""
    due = actionable_followups().filter(so__role=User.Role.CRE, so_id=F("lead__assigned_so_id"))
    return {
        "assigned": Q(),
        **{key: Q(ce_result=key) for key in ("untouched", "qualified", "lost", "in_progress")},
        "followups": Q(pk__in=due.values("lead_id")),
        "awaiting_ps": Q(assigned_ps__isnull=True) & ~Q(status__in=["WON", "LOST", "UNQUALIFIED"]),
        "due_today": Q(pk__in=due.filter(scheduled_for__date=timezone.localdate(now)).values("lead_id")),
        "overdue": Q(pk__in=due.filter(scheduled_for__lt=now).values("lead_id")),
    }


def ce_matching_leads(filters):
    buckets = {**ce_buckets(timezone.now()), "calls": Q(_ce_called=True)}
    metric = filters.params["ce_metric"]
    if metric not in buckets:
        raise ValidationError({"ce_metric": "Choose a CE performance count."})
    return ce_cohort(filters).filter(buckets[metric])


def ce_performance(filters):
    # Every count describes the same currently owned enquiry cohort.
    leads = ce_cohort(filters)
    users = User.objects.for_reporting().filter(role=User.Role.CRE).order_by("first_name", "last_name", "email")
    allocation = leads.filter(pk=OuterRef("lead_id")).values("_ce_allocated_at")[:1]
    calls = CallLog.objects.filter(
        lead_id__in=leads.values("pk"), so_id=F("lead__assigned_so_id"),
        created_at__gte=Subquery(allocation),
    )
    handoffs = LeadAudit.objects.filter(
        lead_id__in=leads.values("pk"), actor_id=F("lead__assigned_so_id"),
        event="assigned_ps", after__assigned_ps__isnull=False, created_at__gte=Subquery(allocation),
    )
    if filters.branches:
        users = users.annotate(_branch=Lower(Trim("location"))).filter(
            Q(_branch__in=filters.branches) | Q(pk__in=leads.values("assigned_so_id"))
            | Q(pk__in=calls.values("so_id")) | Q(pk__in=handoffs.values("actor_id"))
        )
    if filters.employee:
        users = users.filter(pk=filters.employee.pk)
    users = list(users)
    ids = [user.pk for user in users]
    now = timezone.now()
    workload = {row.pop("assigned_so_id"): row for row in leads.filter(
        assigned_so_id__in=ids,
    ).values("assigned_so_id").annotate(
        **{key: Count("pk", filter=predicate, distinct=True) for key, predicate in ce_buckets(now).items()},
    )}
    activity = {row.pop("so_id"): row for row in calls.filter(so_id__in=ids).values("so_id").annotate(
        calls=Count("pk"),
        called=Count("lead_id", distinct=True),
        last_call=Max("created_at"),
    )}
    passed = dict(handoffs.filter(actor_id__in=ids).values("actor_id").annotate(total=Count("lead_id", distinct=True)).values_list("actor_id", "total"))
    fields = ("assigned", "untouched", "qualified", "lost", "in_progress", "followups", "awaiting_ps", "due_today", "overdue", "calls", "called", "handoffs")
    rows = []
    for user in users:
        row = {
            "id": user.pk, "name": user.history_display_name, "email": user.email,
            "branch": user.location, "lifecycle": user.lifecycle_status,
            **dict.fromkeys(fields, 0), "last_call": None,
            **workload.get(user.pk, {}), **activity.get(user.pk, {}), "handoffs": passed.get(user.pk, 0),
        }
        row["qualification_rate"] = round(row["qualified"] / row["assigned"] * 100, 1) if row["assigned"] else None
        rows.append(row)
    summary = {key: sum(row[key] for row in rows) for key in fields}
    return {"results": rows, "summary": summary, "generated_at": now}
