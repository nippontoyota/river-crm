import csv
from calendar import monthrange
from datetime import date, datetime, timedelta

from django.db.models import Case, When, Count, Exists, IntegerField, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce, Trim, TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsAdmin, IsSalesManager
from analytics.cache import cache_analytics
from leads.metrics import CE_HANDLING_FILTERS, PS_HANDLING_FILTERS, actionable_followups, etbr_aggregates, lost_reason_groups, with_ce_handling, with_ps_handling
from leads.models import CallLog, FollowUp, Lead, LeadAudit
from leads.choices import choice_q, merge_choice_counts, unique_choices, color_q, NO_COLOR_PREFERENCE
from leads.metrics import lost_lead_filter
from leads.serializers import configured_values


def csv_value(value):
    if isinstance(value, datetime):
        local_value = timezone.localtime(value) if timezone.is_aware(value) else value
        return local_value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return value


def manager_csv_value(key, value):
    if key == "status":
        value = {Lead.Status.QUALIFIED: "Interested", Lead.Status.UNQUALIFIED: "Not interested"}.get(value, value)
    return csv_value(value)


def metrics(queryset):
    queryset = with_ce_handling(with_ps_handling(queryset))
    counts = queryset.aggregate(
        **etbr_aggregates(),
        total_assigned=Count("id"),
        active_pipeline=Count("id", filter=~Q(status__in=["WON", "LOST", "UNQUALIFIED"]) & ~Q(sales_outcome__in=["RETAILED", "LOST"])),
        total_called=Count("id", filter=~Q(status=Lead.Status.FRESH)),
        untouched_by_ce=Count("id", filter=CE_HANDLING_FILTERS["untouched"]),
        untouched_by_ps=Count("id", filter=PS_HANDLING_FILTERS["untouched"]),
        qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)),
        walkins=Count("id", filter=choice_q("source", Lead.Source.WALKIN)),
        booked=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.BOOKED)),
        won=Count("id", filter=Q(status=Lead.Status.WON)),
        lost=Count("id", filter=Q(status__in=[Lead.Status.LOST, Lead.Status.UNQUALIFIED])),
    )
    counts["conversion_rate"] = percent(counts["won"], counts["total_assigned"])
    return counts


def team_metrics(users, lead_relation):
    today = timezone.localdate()
    # Count calls independently: joining both user leads and user calls multiplies
    # their rows before every DISTINCT aggregate, even though neither count needs it.
    daily_calls = dict(CallLog.objects.filter(so__in=users, created_at__date=today,
        lead__deleted_at__isnull=True).order_by().values("so_id").annotate(total=Count("id")).values_list("so_id", "total"))
    active_leads = Q(**{f"{lead_relation}__deleted_at__isnull": True})
    is_ce = lead_relation == "assigned_leads"
    handled = with_ce_handling(Lead.objects.all()) if is_ce else with_ps_handling(Lead.objects.all())
    untouched = handled.filter((CE_HANDLING_FILTERS if is_ce else PS_HANDLING_FILTERS)["untouched"])
    active_untouched = untouched.exclude(status__in=["WON", "LOST", "UNQUALIFIED"]).exclude(sales_outcome__in=["RETAILED", "LOST"])
    called = handled.filter(**{("_ce_called" if is_ce else "_ps_called"): True})
    rows = []
    for user in users.annotate(
        total_assigned=Count(lead_relation, filter=active_leads, distinct=True),
        followup_untouched=Count(lead_relation, filter=active_leads & Q(**{f"{lead_relation}__pk__in": active_untouched.values("pk")}), distinct=True),
        total_called=Count(lead_relation, filter=active_leads & Q(**{f"{lead_relation}__pk__in": called.values("pk")}), distinct=True),
        untouched=Count(lead_relation, filter=active_leads & Q(**{f"{lead_relation}__pk__in": untouched.values("pk")}), distinct=True),
        qualified=Count(lead_relation, filter=active_leads & Q(**{f"{lead_relation}__status": Lead.Status.QUALIFIED}), distinct=True),
        walkins=Count(lead_relation, filter=active_leads & choice_q(f"{lead_relation}__source", Lead.Source.WALKIN), distinct=True),
        booked=Count(lead_relation, filter=active_leads & Q(**{f"{lead_relation}__sales_outcome": Lead.SalesOutcome.BOOKED}), distinct=True),
        won=Count(lead_relation, filter=active_leads & Q(**{f"{lead_relation}__status": Lead.Status.WON}), distinct=True),
        lost=Count(lead_relation, filter=active_leads & Q(**{f"{lead_relation}__status__in": [Lead.Status.LOST, Lead.Status.UNQUALIFIED]}), distinct=True),
    ):
        rows.append({
            "id": user.id,
            "name": user.get_full_name() or user.email,
            "lifecycle_status": user.lifecycle_status,
            "total_assigned": user.total_assigned,
            "total_called": user.total_called,
            "untouched": user.untouched,
            "followup_untouched": user.followup_untouched,
            "calls_today": daily_calls.get(user.pk, 0),
            "qualified": user.qualified,
            "walkins": user.walkins,
            "booked": user.booked,
            "won": user.won,
            "lost": user.lost,
            "conversion_rate": round((user.won / user.total_assigned) * 100, 1) if user.total_assigned else 0,
        })
    return rows


def percent(part, whole):
    return round((part / whole) * 100, 1) if whole else 0


def period_bounds(request):
    today = timezone.localdate()
    date_range = request.query_params.get("range", "mtd")
    if date_range == "today":
        start = end = today
    elif date_range == "all":
        start = end = None
    elif request.query_params.get("date_from") or request.query_params.get("date_to"):
        date_range = "custom"
        start = parse_date(request.query_params.get("date_from", "")) if request.query_params.get("date_from") else None
        end = parse_date(request.query_params.get("date_to", "")) if request.query_params.get("date_to") else None
    else:
        start = today.replace(day=1)
        end = today
    return date_range, start, end


def previous_mtd_bounds(start, end):
    if not start or not end or start.day != 1:
        return None, None
    year = start.year if start.month > 1 else start.year - 1
    month = start.month - 1 or 12
    last_day = monthrange(year, month)[1]
    return start.replace(year=year, month=month, day=1), end.replace(year=year, month=month, day=min(end.day, last_day))


def with_period(queryset, start, end, field="enquiry_date"):
    if start:
        queryset = queryset.filter(**{f"{field}__gte": start})
    if end:
        queryset = queryset.filter(**{f"{field}__lte": end})
    return queryset


def manager_base_queryset(request, include_ps=True):
    branch = request.user.location.strip()
    if not branch:
        return Lead.objects.none()
    queryset = Lead.objects.filter(choice_q("branch", branch), deleted_at__isnull=True)
    if value := request.query_params.get("source"):
        queryset = queryset.filter(choice_q("source", value))
    if value := request.query_params.get("model"):
        queryset = queryset.filter(model_interest__icontains=value.strip())
    if value := request.query_params.get("color"):
        queryset = queryset.filter(color_q("qualification__variant", value))
    if value := request.query_params.get("category"):
        queryset = queryset.filter(category=value)
    if value := request.query_params.get("status"):
        queryset = queryset.filter(status=value)
    if include_ps and (value := request.query_params.get("ps")):
        queryset = queryset.filter(assigned_ps_id=value)
    return queryset


def ps_followup_queryset(request):
    _, start, end = period_bounds(request)
    queryset = with_period(manager_base_queryset(request, include_ps=False), start, end).filter(assigned_ps__isnull=False).exclude(lost_lead_filter())
    if priority := request.query_params.get("priority", "").upper():
        if priority in {choice for choice, _ in Lead.Category.choices}:
            queryset = queryset.filter(category=priority)
    followup_count = FollowUp.objects.filter(lead_id=OuterRef("pk"), so_id=OuterRef("assigned_ps_id")).values("lead_id").annotate(total=Count("id")).values("total")
    overdue_followup = actionable_followups().filter(lead_id=OuterRef("pk"), so_id=OuterRef("assigned_ps_id"), scheduled_for__lt=timezone.now())
    test_drive_call = CallLog.objects.filter(lead_id=OuterRef("pk"), so_id=OuterRef("assigned_ps_id"), outcome__iexact="Need Test Drive")
    return with_ps_handling(queryset).annotate(
        ps_followup_count=Coalesce(Subquery(followup_count, output_field=IntegerField()), Value(0)),
        has_overdue_followup=Exists(overdue_followup),
        has_test_drive_call=Exists(test_drive_call),
    )


def has_test_drive(qualification_value, call_value):
    return bool(call_value or (qualification_value and qualification_value.strip().casefold() != "no"))


def ps_followup_payload(request):
    queryset = ps_followup_queryset(request)
    primary = request.query_params.get("ps", "")
    compare = request.query_params.get("compare_ps", "") if primary else ""
    selected_ids = {int(value) for value in (primary, compare) if value.isdigit()}
    if selected_ids:
        queryset = queryset.filter(assigned_ps_id__in=selected_ids)

    bucket = request.query_params.get("bucket", "")
    allowed_buckets = {"total", "test_drive", "unattended", "overdue", "f1", "f2", "f3", "f4", "f5"}
    if bucket:
        if bucket not in allowed_buckets or not primary.isdigit():
            return {"rows": [], "leads": []}
        queryset = queryset.filter(assigned_ps_id=int(primary))
        if bucket == "test_drive":
            queryset = queryset.filter(
                Q(has_test_drive_call=True)
                | (Q(qualification__test_drive__isnull=False) & ~Q(qualification__test_drive="") & ~Q(qualification__test_drive__iexact="No"))
            )
        elif bucket == "unattended":
            queryset = queryset.filter(PS_HANDLING_FILTERS["untouched"])
        elif bucket == "overdue":
            queryset = queryset.filter(has_overdue_followup=True)
        elif bucket == "f5":
            queryset = queryset.filter(ps_followup_count__gte=5)
        elif bucket.startswith("f"):
            queryset = queryset.filter(ps_followup_count=int(bucket[1:]))
        leads = []
        for lead in queryset.select_related("qualification").order_by("-created_at"):
            qualification = getattr(lead, "qualification", None)
            qualification_value = qualification.test_drive if qualification else ""
            leads.append({
                "id": lead.id,
                "name": lead.name,
                "phone": lead.phone,
                "source": lead.source,
                "created_at": lead.created_at,
                "model": lead.model_interest,
                "test_drive": qualification_value if qualification_value and qualification_value.casefold() != "no" else "Yes" if lead.has_test_drive_call else "No",
                "status": lead.status,
            })
        return {"rows": [], "leads": leads}

    grouped = {}
    empty_counts = {"total_leads": 0, "test_drive": 0, "unattended": 0, "overdue": 0, "f1": 0, "f2": 0, "f3": 0, "f4": 0, "f5": 0}
    for lead in queryset.values("assigned_ps_id", "_ps_touched", "ps_followup_count", "qualification__test_drive", "has_test_drive_call", "has_overdue_followup"):
        row = grouped.setdefault(lead["assigned_ps_id"], empty_counts.copy())
        row["total_leads"] += 1
        count = lead["ps_followup_count"]
        row["test_drive"] += int(has_test_drive(lead["qualification__test_drive"], lead["has_test_drive_call"]))
        row["overdue"] += int(lead["has_overdue_followup"])
        if not lead["_ps_touched"]:
            row["unattended"] += 1
        if count >= 5:
            row["f5"] += 1
        elif count:
            row[f"f{count}"] += 1

    branch = request.user.location.strip()
    users = User.objects.filter(role=User.Role.SALES_OFFICER, is_active=True).filter(choice_q("location", branch) | Q(id__in=grouped))
    if selected_ids:
        users = users.filter(id__in=selected_ids)
    rows = [{"id": user.id, "name": user.get_full_name() or user.email, "email": user.email, **grouped.get(user.id, empty_counts)} for user in users.order_by("first_name", "last_name", "email")]
    return {"rows": rows, "leads": []}


def summary_for(queryset, stale_since=None):
    aggregates = dict(
        **etbr_aggregates(),
        total=Count("id"),
        untouched=Count("id", filter=PS_HANDLING_FILTERS["untouched"]),
        contacted=Count("id", filter=~Q(status=Lead.Status.FRESH)),
        open=Count("id", filter=~Q(status__in=[Lead.Status.WON, Lead.Status.LOST, Lead.Status.UNQUALIFIED])),
        qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)),
        walkin=Count("id", filter=choice_q("source", Lead.Source.WALKIN)),
        booked=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.BOOKED)),
        retailed=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.RETAILED)),
        lost=Count("id", filter=Q(status__in=[Lead.Status.LOST, Lead.Status.UNQUALIFIED])),
        flagged=Count("id", filter=Q(flagged_to_manager=True)),
    )
    if stale_since:
        aggregates["stale_untouched"] = Count("id", filter=Q(status=Lead.Status.FRESH, created_at__date__lte=stale_since))
    data = with_ps_handling(queryset).aggregate(**aggregates)
    data["lead_to_qualified_rate"] = percent(data["qualified"], data["total"])
    data["lead_to_retail_rate"] = percent(data["retailed"], data["total"])
    data["qualified_to_booked_rate"] = percent(data["booked"], data["qualified"])
    data["booked_to_retail_rate"] = percent(data["retailed"], data["booked"])
    return data


def with_deltas(current, previous):
    if not previous:
        return {**current, "delta": {}}
    return {**current, "delta": {key: round(current[key] - previous.get(key, 0), 1) for key in ("total", "untouched", "qualified", "booked", "retailed", "lost", "lead_to_retail_rate")}}


def source_rows(queryset):
    rows = list(queryset.values("source").annotate(total=Count("id"), qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)), booked=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.BOOKED)), retailed=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.RETAILED)), lost=Count("id", filter=Q(status__in=[Lead.Status.LOST, Lead.Status.UNQUALIFIED]))).order_by("-total", "source"))
    rows = merge_choice_counts(rows, "source", configured_values("sources"))
    for row in rows:
        row["conversion_rate"] = percent(row["retailed"], row["total"])
    return rows


def model_rows(queryset):
    rows = list(queryset.values("model_interest").annotate(total=Count("id"), qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)), booked=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.BOOKED)), retailed=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.RETAILED)), lost=Count("id", filter=Q(status__in=[Lead.Status.LOST, Lead.Status.UNQUALIFIED]))).order_by("-total", "model_interest"))
    rows = merge_choice_counts(rows, "model_interest", configured_values("models"))
    for row in rows:
        row["model"] = row.pop("model_interest") or "Model not set"
        row["conversion_rate"] = percent(row["retailed"], row["total"])
    return rows


def color_rows(queryset):
    color = Case(When(color_q("qualification__variant", NO_COLOR_PREFERENCE), then=Value(NO_COLOR_PREFERENCE)), default=Trim("qualification__variant"))
    rows = list(queryset.annotate(color=color).values("color").annotate(total=Count("id"), qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)), booked=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.BOOKED)), retailed=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.RETAILED)), lost=Count("id", filter=Q(status__in=[Lead.Status.LOST, Lead.Status.UNQUALIFIED]))).order_by("-total", "color"))
    rows = merge_choice_counts(rows, "color", configured_values("colorVariants"))
    for row in rows:
        row["conversion_rate"] = percent(row["retailed"], row["total"])
    return rows


def role_rows(users, lead_relation, branch, start, end, scoped_leads=None):
    untouched_leads = with_ps_handling(Lead.objects.all()).filter(PS_HANDLING_FILTERS["untouched"])
    lead_filter = Q(**{f"{lead_relation}__deleted_at__isnull": True}) & choice_q(f"{lead_relation}__branch", branch)
    if start:
        lead_filter &= Q(**{f"{lead_relation}__enquiry_date__gte": start})
    if end:
        lead_filter &= Q(**{f"{lead_relation}__enquiry_date__lte": end})
    if scoped_leads is not None:
        lead_ids = scoped_leads.values("pk")
        lead_filter &= Q(**{f"{lead_relation}__pk__in": lead_ids})

    activity_filter = Q(lead__deleted_at__isnull=True) & choice_q("lead__branch", branch)
    if scoped_leads is not None:
        activity_filter &= Q(lead__pk__in=scoped_leads.values("pk"))
    calls = CallLog.objects.filter(activity_filter)
    followups = FollowUp.objects.filter(activity_filter)
    if start:
        calls = calls.filter(created_at__date__gte=start)
        followups = followups.filter(scheduled_for__date__gte=start)
    if end:
        calls = calls.filter(created_at__date__lte=end)
        followups = followups.filter(scheduled_for__date__lte=end)
    # Separate one-to-many aggregates avoid a leads × calls × follow-ups join.
    calls_by_user = {
        row["so_id"]: row
        for row in calls.values("so_id").annotate(calls=Count("id"), last_activity=Max("created_at"))
    }
    followups_by_user = dict(followups.values_list("so_id").annotate(total=Count("id")))

    rows = []
    for user in users.annotate(
        total=Count(lead_relation, filter=lead_filter),
        untouched=Count(lead_relation, filter=lead_filter & Q(**{f"{lead_relation}__pk__in": untouched_leads.values("pk")})),
        qualified=Count(lead_relation, filter=lead_filter & Q(**{f"{lead_relation}__status": Lead.Status.QUALIFIED})),
        booked=Count(lead_relation, filter=lead_filter & Q(**{f"{lead_relation}__sales_outcome": Lead.SalesOutcome.BOOKED})),
        retailed=Count(lead_relation, filter=lead_filter & Q(**{f"{lead_relation}__sales_outcome": Lead.SalesOutcome.RETAILED})),
        lost=Count(lead_relation, filter=lead_filter & Q(**{f"{lead_relation}__status__in": [Lead.Status.LOST, Lead.Status.UNQUALIFIED]})),
    ):
        call_data = calls_by_user.get(user.id, {})
        call_count = call_data.get("calls", 0)
        followup_count = followups_by_user.get(user.id, 0)
        if not (user.total or call_count or followup_count or user.location.strip().casefold() == branch.casefold()):
            continue
        rows.append({
            "id": user.id,
            "name": user.get_full_name() or user.email,
            "email": user.email,
            "location": user.location,
            "total": user.total,
            "untouched": user.untouched,
            "qualified": user.qualified,
            "booked": user.booked,
            "retailed": user.retailed,
            "lost": user.lost,
            "calls": call_count,
            "followups": followup_count,
            "last_activity": call_data.get("last_activity"),
            "conversion_rate": percent(user.retailed, user.total),
            "qualification_rate": percent(user.qualified, user.total),
        })
    return rows


def manager_payload(request):
    date_range, start, end = period_bounds(request)
    branch = request.user.location.strip()
    scoped = manager_base_queryset(request)
    queryset = with_period(scoped, start, end)
    requested = {value for value in request.query_params.get("include", "").split(",") if value}
    includes = requested or {"overview", "ps", "source", "ops"}
    prev_start, prev_end = previous_mtd_bounds(start, end) if date_range == "mtd" else (None, None)
    previous = summary_for(with_period(manager_base_queryset(request), prev_start, prev_end)) if prev_start and prev_end else {}
    today = timezone.localdate()
    stale_since = today - timedelta(days=3)
    summary = with_deltas(summary_for(queryset, stale_since), previous)
    followups = {"due": 0, "overdue": 0, "by_owner": []}
    if "overview" in includes or "ps" in includes:
        due_followups = actionable_followups().filter(lead__in=queryset, so__role=User.Role.SALES_OFFICER, scheduled_for__date__lte=today)
        owner_rows = list(due_followups.values("so__id", "so__first_name", "so__last_name", "so__email").annotate(
            count=Count("lead_id", distinct=True),
            overdue=Count("lead_id", filter=Q(scheduled_for__lt=timezone.now()), distinct=True),
        ).order_by("-count"))
        followups = {
            "due": sum(row["count"] for row in owner_rows),
            "overdue": sum(row.pop("overdue") for row in owner_rows),
            "by_owner": owner_rows,
        }
    summary["followups_due"] = followups["due"]
    funnel_counts = [("total", "Leads", summary["total"]), ("contacted", "Contacted", summary["contacted"]), ("qualified", "Qualified", summary["qualified"]), ("booked", "Booked", summary["booked"]), ("retailed", "Retailed", summary["retailed"])]
    funnel = [{"key": key, "label": label, "count": count, "rate": percent(count, summary["total"])} for key, label, count in funnel_counts]
    payload = {
        "range": date_range,
        "date_from": start,
        "date_to": end,
        "branch": branch,
        "summary": summary,
        "funnel": funnel,
        "cre": [], "ps": [], "source": [], "models": [], "colors": [], "status": [], "categories": [], "monthly": [],
        "followups": followups, "lost_reasons": [], "stale_leads": [],
        "generated_at": timezone.now(),
    }
    if "overview" in includes:
        payload["monthly"] = list(queryset.annotate(month=TruncMonth("enquiry_date")).values("month").annotate(total=Count("id"), qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)), booked=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.BOOKED)), retailed=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.RETAILED))).order_by("month"))
    if "ps" in includes:
        filtered_leads = scoped if any(request.query_params.get(key) for key in ("source", "model", "color", "category", "status", "ps")) else None
        payload["ps"] = role_rows(User.objects.filter(role=User.Role.SALES_OFFICER, is_active=True), "ps_leads", branch, start, end, filtered_leads)
    if "source" in includes:
        payload["source"] = source_rows(queryset)
        payload["models"] = model_rows(queryset)
    if "source" in includes or "colors" in includes:
        payload["colors"] = color_rows(queryset)
    if "lost" in includes:
        payload["status"] = list(queryset.filter(status__in=[Lead.Status.LOST, Lead.Status.UNQUALIFIED]).values("status").annotate(count=Count("id")).order_by("status"))
        payload["lost_reasons"] = [{"reason": group["reason"], "count": len(group["ids"])} for group in lost_reason_groups(queryset)]
    if "ops" in includes:
        payload["status"] = list(queryset.values("status").annotate(count=Count("id")).order_by("-count"))
        payload["categories"] = list(queryset.values("category").annotate(count=Count("id")).order_by("category"))
        if "lost" not in includes:
            payload["lost_reasons"] = [{"reason": group["reason"], "count": len(group["ids"])} for group in lost_reason_groups(queryset)]
        payload["stale_leads"] = list(queryset.filter(status=Lead.Status.FRESH, created_at__date__lte=stale_since).order_by("created_at").values("id", "name", "phone", "source", "model_interest", "created_at")[:20])
    if "filters" in includes:
        pairs = list(queryset.values("source", "model_interest", "assigned_ps_id").distinct())
        owner_ids = {row["assigned_ps_id"] for row in pairs if row["assigned_ps_id"]}
        users = User.objects.filter(is_active=True, role=User.Role.SALES_OFFICER).filter(choice_q("location", branch) | Q(id__in=owner_ids)).order_by("first_name", "last_name", "email")
        payload["filters"] = {
            "source": sorted(unique_choices(row["source"] for row in pairs)),
            "models": sorted(unique_choices(row["model_interest"] for row in pairs)),
            "cre": [],  # Retain the response shape for older clients without exposing CE data.
            "ps": [{"id": user.id, "name": user.get_full_name() or user.email} for user in users],
        }
    return payload


class AdminAnalyticsView(APIView):
    permission_classes = [IsAdmin]

    @cache_analytics("admin")
    def get(self, request):
        queryset = Lead.objects.filter(deleted_at__isnull=True)
        source = list(queryset.values("source").annotate(total=Count("id"), qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)), won=Count("id", filter=Q(status=Lead.Status.WON))).order_by("source"))
        source = merge_choice_counts(source, "source")
        visible_users = User.objects.for_reporting()
        cre = team_metrics(visible_users.filter(role=User.Role.CRE), "assigned_leads")
        officers = team_metrics(visible_users.filter(role=User.Role.SALES_OFFICER), "ps_leads")
        return Response({"summary": metrics(queryset), "source": source, "cre": cre, "officers": officers, "generated_at": timezone.now()})


class MyAnalyticsView(APIView):
    @cache_analytics("personal")
    def get(self, request):
        owner_filter = {"assigned_so": request.user} if request.user.role == User.Role.CRE else {"assigned_ps": request.user}
        queryset = Lead.objects.filter(deleted_at__isnull=True, **owner_filter)
        is_ce = request.user.role == User.Role.CRE
        queryset = with_ce_handling(queryset) if is_ce else with_ps_handling(queryset)
        date_range = request.query_params.get("range", "mtd")
        today = timezone.localdate()
        if date_range == "today":
            queryset = queryset.filter(enquiry_date=today)
        elif date_range == "mtd":
            queryset = queryset.filter(enquiry_date__year=today.year, enquiry_date__month=today.month)
        elif request.query_params.get("date_from"):
            queryset = queryset.filter(enquiry_date__gte=request.query_params["date_from"])
            if request.query_params.get("date_to"):
                queryset = queryset.filter(enquiry_date__lte=request.query_params["date_to"])
        status_aggregates = {f"status_{value.lower()}": Count("id", filter=Q(status=value)) for value, _ in Lead.Status.choices}
        summary = queryset.aggregate(
            **etbr_aggregates(),
            total=Count("id"),
            untouched=Count("id", filter=(CE_HANDLING_FILTERS if is_ce else PS_HANDLING_FILTERS)["untouched"]),
            qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)),
            booked=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.BOOKED)),
            lost=Count("id", filter=Q(status__in=[Lead.Status.LOST, Lead.Status.UNQUALIFIED])),
            retailed=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.RETAILED)),
            **status_aggregates,
        )
        status_counts = [{"status": value, "count": summary.pop(f"status_{value.lower()}")} for value, _ in Lead.Status.choices if summary[f"status_{value.lower()}"]]
        summary["assigned"] = summary["total"]
        summary["conversion_rate"] = round((summary["retailed"] / summary["total"]) * 100, 1) if summary["total"] else 0
        source = list(queryset.values("source").annotate(total=Count("id"), qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)), booked=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.BOOKED)), retailed=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.RETAILED))).order_by("-total"))
        models = list(queryset.values("model_interest").annotate(total=Count("id"), qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)), booked=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.BOOKED))).order_by("-total"))
        source = merge_choice_counts(source, "source")
        models = merge_choice_counts(models, "model_interest")
        monthly = list(queryset.annotate(month=TruncMonth("enquiry_date")).values("month").annotate(total=Count("id"), qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED)), booked=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.BOOKED)), retailed=Count("id", filter=Q(sales_outcome=Lead.SalesOutcome.RETAILED))).order_by("month"))
        return Response({"range": date_range, "summary": summary, "status_counts": status_counts, "source": source, "models": models, "monthly": monthly, "generated_at": timezone.now()})


class MyAnalyticsExportView(APIView):
    def get(self, request):
        owner_filter = {"assigned_so": request.user} if request.user.role == User.Role.CRE else {"assigned_ps": request.user}
        queryset = Lead.objects.filter(deleted_at__isnull=True, **owner_filter).order_by("-enquiry_date")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="incheon-my-analytics.csv"'
        writer = csv.writer(response)
        writer.writerow(["Lead", "Phone", "Source", "Model", "Status", "Sales outcome", "Enquiry date", "Branch"])
        writer.writerows([[csv_value(value) for value in row] for row in queryset.values_list("name", "phone", "source", "model_interest", "status", "sales_outcome", "enquiry_date", "branch")])
        return response


class ReceptionistAnalyticsView(APIView):
    @cache_analytics("receptionist")
    def get(self, request):
        if getattr(request.user, "role", None) != "RECEPTIONIST":
            return Response(status=403)
        today = timezone.localdate()
        # Find leads created by this receptionist today
        created_lead_ids = LeadAudit.objects.filter(actor=request.user, event="created", created_at__date=today).values_list("lead_id", flat=True)
        queryset = Lead.objects.filter(choice_q("source", Lead.Source.WALKIN), id__in=created_lead_ids, deleted_at__isnull=True)
        branch = request.user.location.strip()
        queryset = queryset.filter(choice_q("branch", branch)) if branch else queryset.none()
        summary = queryset.aggregate(**etbr_aggregates(), total=Count("id"), walkin=Count("id", filter=choice_q("source", Lead.Source.WALKIN)))
        total = summary["total"]
        walkins = summary["walkin"]
        digital = total - walkins
        # Breakdown by SO assignment
        so_breakdown = list(queryset.values("assigned_ps__first_name", "assigned_ps__last_name", "assigned_ps__email").annotate(count=Count("id")).order_by("-count"))
        formatted_so_breakdown = [
            {
                "name": f"{so['assigned_ps__first_name'] or ''} {so['assigned_ps__last_name'] or ''}".strip() or so["assigned_ps__email"] or "Unassigned",
                "count": so["count"]
            }
            for so in so_breakdown
        ]
        return Response({
            "summary": {
                **summary,
                "total": total,
                "walkin": walkins,
                "digital": digital
            },
            "so_breakdown": formatted_so_breakdown,
            "generated_at": timezone.now()
        })


class SalesManagerAnalyticsView(APIView):
    permission_classes = [IsSalesManager]

    @cache_analytics("sales-manager-ps-calls", max_ttl=60)
    def get(self, request):
        return Response(manager_payload(request))


class SalesManagerPSFollowupsView(APIView):
    permission_classes = [IsSalesManager]

    @cache_analytics("sales-manager-ps-followups-calls")
    def get(self, request):
        return Response(ps_followup_payload(request))


class SalesManagerAnalyticsExportView(APIView):
    permission_classes = [IsSalesManager]

    def get(self, request):
        section = request.query_params.get("section", "ps")
        if section in {"cre", "ce"}:
            return Response({"detail": "CE performance is not available to sales managers."}, status=403)
        if section == "ps_followups":
            data = ps_followup_payload(request)
            rows = data["leads"] or data["rows"]
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="incheon-sales-manager-ps-followups.csv"'
            writer = csv.writer(response)
            if rows:
                keys = list(rows[0].keys())
                writer.writerow(keys)
                writer.writerows([[manager_csv_value(key, row.get(key, "")) for key in keys] for row in rows])
            else:
                writer.writerow(["No matching PS follow-up records"])
            return response
        data = manager_payload(request)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="incheon-sales-manager-{section}.csv"'
        writer = csv.writer(response)
        rows = data.get(section, [])
        if section in {"ps", "source", "models", "colors", "lost_reasons", "stale_leads"} and isinstance(rows, list) and rows:
            keys = [key for key in rows[0] if "qualif" not in key and not (section == "ps" and key == "calls")]
            writer.writerow(keys)
            for row in rows:
                writer.writerow([manager_csv_value(key, row.get(key, "")) for key in keys])
        else:
            writer.writerow(["metric", "value"])
            for key, value in data["summary"].items():
                if key != "delta" and "qualif" not in key:
                    writer.writerow([key, value])
        return response
