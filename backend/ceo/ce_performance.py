"""CE workload and recorded CE activity, independent of later sales outcomes."""
from django.db.models import Count, F, Max, Q
from django.db.models.functions import Lower, Trim
from django.utils import timezone

from accounts.models import User
from leads.metrics import CE_HANDLING_FILTERS, actionable_followups, with_ce_handling
from leads.models import CallLog, LeadAudit


def ce_performance(filters):
    # Ownership is current; activity belongs to the actor, even after reassignment.
    leads = filters.base_leads(employee=False)
    users = User.objects.filter(role=User.Role.CRE).exclude(
        Q(deleted_at__isnull=False) & (Q(first_name__istartswith="test") | Q(last_name__istartswith="test"))
    ).order_by("first_name", "last_name", "email")
    calls = filters.period(CallLog.objects.filter(lead_id__in=leads.values("pk")), "created_at__date")
    handoffs = filters.period(LeadAudit.objects.filter(
        lead_id__in=leads.values("pk"), event="assigned_ps", after__assigned_ps__isnull=False,
    ), "created_at__date")
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
    due = actionable_followups().filter(so__role=User.Role.CRE, so_id=F("lead__assigned_so_id"))
    workload = {row.pop("assigned_so_id"): row for row in with_ce_handling(leads).filter(
        assigned_so_id__in=ids,
    ).values("assigned_so_id").annotate(
        assigned=Count("pk", distinct=True),
        untouched=Count("pk", filter=CE_HANDLING_FILTERS["untouched"], distinct=True),
        awaiting_ps=Count("pk", filter=Q(assigned_ps__isnull=True) & ~Q(status__in=["WON", "LOST", "UNQUALIFIED"]), distinct=True),
        due_today=Count("pk", filter=Q(pk__in=due.filter(scheduled_for__date=timezone.localdate()).values("lead_id")), distinct=True),
        overdue=Count("pk", filter=Q(pk__in=due.filter(scheduled_for__lt=now).values("lead_id")), distinct=True),
    )}
    activity = {row.pop("so_id"): row for row in calls.filter(so_id__in=ids).values("so_id").annotate(
        calls=Count("pk"),
        called=Count("lead_id", distinct=True),
        qualified=Count("lead_id", filter=Q(status="QUALIFIED"), distinct=True),
        not_interested=Count("lead_id", filter=Q(status__in=["LOST", "UNQUALIFIED"]), distinct=True),
        last_call=Max("created_at"),
    )}
    passed = dict(handoffs.filter(actor_id__in=ids).values("actor_id").annotate(total=Count("lead_id", distinct=True)).values_list("actor_id", "total"))
    fields = ("assigned", "untouched", "awaiting_ps", "due_today", "overdue", "calls", "called", "qualified", "not_interested", "handoffs")
    rows = []
    for user in users:
        row = {
            "id": user.pk, "name": user.history_display_name, "email": user.email,
            "branch": user.location, "lifecycle": user.lifecycle_status,
            **dict.fromkeys(fields, 0), "last_call": None,
            **workload.get(user.pk, {}), **activity.get(user.pk, {}), "handoffs": passed.get(user.pk, 0),
        }
        row["qualification_rate"] = round(row["qualified"] / row["called"] * 100, 1) if row["called"] else None
        rows.append(row)
    summary = {key: sum(row[key] for row in rows) for key in fields}
    return {"results": rows, "summary": summary, "generated_at": now}
