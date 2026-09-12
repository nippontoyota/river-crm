from calendar import monthrange
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Max, Q, Sum
from django.db.models.functions import Lower, Trim, TruncMonth
from django.utils import timezone

from accounts.models import User
from complaints.models import Complaint
from leads.models import FollowUp, Lead, SystemConfig
from .finance import TARGET_FIELDS, signed_amount
from .filters import AGE_BANDS, ROLES, ReportFilters
from .models import FinancialEntry, Milestone, OperationEvent, SaleAccount, SalesTarget
from .tracking import branch_key

KINDS = "ETBR"
CLOSED = ["WON", "LOST", "UNQUALIFIED"]
TARGET_DIMENSIONS = ("rto", "source", "campaign", "activity", "sub_activity", "model_interest", "status", "category", "followup", "age", "q")


def targets_applicable(filters):
    return bool(filters.target_month()) and not any(filters.params.get(key) for key in TARGET_DIMENSIONS)


def ratio(numerator, denominator):
    return round(numerator * 100 / denominator, 1) if denominator else None


def milestone_counts(queryset):
    return queryset.aggregate(**{kind: Count("lead_id", filter=Q(kind=kind), distinct=True) for kind in KINDS})


def current_counts(queryset):
    open_followups = FollowUp.objects.filter(resolved_at__isnull=True)
    return queryset.aggregate(
        leads=Count("id", distinct=True), active=Count("id", filter=~Q(status__in=CLOSED), distinct=True),
        booked=Count("id", filter=Q(sales_outcome="BOOKED"), distinct=True),
        retailed=Count("id", filter=Q(sales_outcome="RETAILED"), distinct=True),
        lost=Count("id", filter=Q(status__in=["LOST", "UNQUALIFIED"]), distinct=True),
        overdue=Count("id", filter=Q(pk__in=open_followups.filter(scheduled_for__lt=timezone.now()).values("lead_id")) & ~Q(status__in=CLOSED), distinct=True),
        unassigned=Count("id", filter=(Q(assigned_so__isnull=True, assigned_ps__isnull=True) | Q(status="QUALIFIED", assigned_ps__isnull=True)) & ~Q(status__in=CLOSED), distinct=True),
        missing_next_action=Count("id", filter=~Q(pk__in=open_followups.values("lead_id")) & ~Q(status__in=CLOSED), distinct=True),
        reassignment=Count("id", filter=Q(needs_cre_reassignment=True) | Q(needs_so_reassignment=True), distinct=True),
        incomplete=Count("id", filter=Q(rto="") | Q(branch=""), distinct=True),
        flagged=Count("id", filter=Q(flagged_to_manager=True), distinct=True),
        missing_finance=Count("id", filter=Q(sales_outcome__in=["BOOKED", "RETAILED"]) & (Q(sale_account__isnull=True) | Q(sale_account__agreed_amount__isnull=True)), distinct=True),
    )


def conversions(filters):
    # Transition conversion is measured within the enquiry cohort; period counts
    # are independent achievements and must never be divided as a funnel.
    cohort = filters.period(filters.base_leads(), "enquiry_date")
    e = cohort.count()
    counts = cohort.aggregate(
        t=Count("id", filter=Q(milestones__kind="T"), distinct=True),
        b=Count("id", filter=Q(milestones__kind="B"), distinct=True),
        r=Count("id", filter=Q(milestones__kind="R"), distinct=True))
    # A later milestone must be dated on/after its predecessor. Unknown dates
    # and skipped stages cannot produce a transition conversion.
    from django.db.models import OuterRef, Subquery
    t_date = Milestone.objects.filter(lead_id=OuterRef("lead_id"), kind="T", occurred_on__isnull=False).values("occurred_on")[:1]
    b_date = Milestone.objects.filter(lead_id=OuterRef("lead_id"), kind="B", occurred_on__isnull=False).values("occurred_on")[:1]
    tb = Milestone.objects.filter(kind="B", lead__in=cohort).annotate(previous=Subquery(t_date)).filter(occurred_on__gte=F("previous")).count()
    br = Milestone.objects.filter(kind="R", lead__in=cohort).annotate(previous=Subquery(b_date)).filter(occurred_on__gte=F("previous")).count()
    return {"E_T": ratio(counts["t"], e), "E_B": ratio(counts["b"], e), "E_R": ratio(counts["r"], e),
            "T_B": ratio(tb, counts["t"]), "B_R": ratio(br, counts["b"]), "cohort_size": e}


def target_summary(filters, branch=None, so=None):
    month = filters.target_month()
    if not targets_applicable(filters):
        return {"available": False, "reason": "Targets apply to monthly branch or SO results."}
    qs = SalesTarget.objects.filter(month=month)
    if branch is not None:
        qs = qs.filter(branch=branch)
    elif filters.branches:
        qs = qs.filter(branch__in=filters.branches)
    if so is not None:
        qs = qs.filter(so_id=so)
    elif filters.employee:
        if filters.employee.role == "SO":
            qs = qs.filter(so=filters.employee)
        elif filters.employee.role == "SALES_MANAGER":
            qs = qs.filter(branch=branch_key(filters.employee.location), so__isnull=True)
        else:
            return {"available": False, "reason": "Targets are set for branches and SOs."}
    elif filters.params.get("role"):
        return {"available": False, "reason": "Select a branch or individual SO for targets."}
    else:
        qs = qs.filter(so__isnull=True)
    totals = qs.aggregate(**{key: Sum(key) for key in TARGET_FIELDS})
    allocations = SalesTarget.objects.filter(month=month, so__isnull=False)
    if branch is not None:
        allocations = allocations.filter(branch=branch)
    elif filters.branches:
        allocations = allocations.filter(branch__in=filters.branches)
    allocated = allocations.aggregate(**{key: Sum(key) for key in TARGET_FIELDS})
    missing_branches = set(filters.branches or branch_options()) - set(qs.values_list("branch", flat=True)) if so is None and not filters.employee else set()
    return {"available": qs.exists(), "month": month, "values": totals, "allocated": allocated,
            "allocation_gap": {key: (totals[key] or 0) - (allocated[key] or 0) for key in TARGET_FIELDS},
            "missing_branches": sorted(missing_branches - {"", "__unknown__"})}


def branch_options():
    lists = (SystemConfig.objects.filter(pk=1).values_list("lists", flat=True).first() or {}).get("branches", [])
    values = [*lists, *Lead.objects.values_list("branch", flat=True).distinct(), *User.objects.values_list("location", flat=True).distinct(), *Complaint.objects.values_list("branch", flat=True).distinct(), *Milestone.objects.values_list("branch", flat=True).distinct()]
    result = {}
    for value in values:
        key = branch_key(value)
        if key:
            result.setdefault(key, value.strip())
    return result


def financial_accounts(filters):
    return SaleAccount.objects.filter(lead__in=filters.base_leads(include_archived=True)).select_related("lead").annotate(net_collected=Sum(signed_amount_for_account()))


def signed_amount_for_account():
    from django.db.models import Case, DecimalField, Value, When
    return Case(When(entries__kind="PAYMENT", then=F("entries__amount")), When(entries__kind="REFUND", then=-F("entries__amount")),
        When(entries__kind="REVERSAL", entries__reverses__kind="PAYMENT", then=-F("entries__amount")),
        When(entries__kind="REVERSAL", entries__reverses__kind="REFUND", then=F("entries__amount")), default=Value(Decimal("0")), output_field=DecimalField(max_digits=15, decimal_places=2))


def account_row(account):
    lead = account.lead
    net = account.net_collected or Decimal("0")
    confirmed = account.retail_amount if lead.sales_outcome == "RETAILED" else account.agreed_amount
    cancelled = lead.status in ["LOST", "UNQUALIFIED"]
    outstanding = max(confirmed - net, Decimal("0")) if confirmed is not None and not cancelled else None
    credit = max(net - confirmed, Decimal("0")) if confirmed is not None and not cancelled else Decimal("0")
    mismatch = (lead.sales_outcome == "RETAILED" and account.retail_amount is None) or (lead.sales_outcome != "RETAILED" and account.retail_amount is not None)
    return {"id": account.id, "lead_id": lead.id, "name": lead.name, "branch": lead.branch, "rto": lead.rto,
        "status": lead.status, "sales_outcome": lead.sales_outcome, "agreed_amount": account.agreed_amount,
        "retail_amount": account.retail_amount, "confirmed_on": account.confirmed_on, "net_collected": net,
        "outstanding": outstanding, "customer_credit": credit, "retained_on_cancelled": net if cancelled else Decimal("0"),
        "needs_review": mismatch, "archived": bool(lead.deleted_at), "updated_at": account.updated_at}


def financial_summary(filters):
    from django.db.models import Case, DecimalField, Value, When
    from django.db.models.functions import Coalesce, Greatest
    money = DecimalField(max_digits=15, decimal_places=2)
    zero = Value(Decimal("0"), output_field=money)
    accounts = financial_accounts(filters).annotate(net=Coalesce("net_collected", zero),
        customer_amount=Case(When(lead__sales_outcome="RETAILED", then=F("retail_amount")), default=F("agreed_amount"), output_field=money))
    active = ~Q(lead__status__in=["LOST", "UNQUALIFIED"])
    accounts = accounts.annotate(
        due=Case(When(active & Q(customer_amount__isnull=False), then=Greatest(F("customer_amount") - F("net"), zero)), default=zero, output_field=money),
        credit=Case(When(active & Q(customer_amount__isnull=False), then=Greatest(F("net") - F("customer_amount"), zero)), default=zero, output_field=money),
        retained=Case(When(lead__status__in=["LOST", "UNQUALIFIED"], then=F("net")), default=zero, output_field=money))
    balances = accounts.aggregate(outstanding=Sum("due"), customer_credit=Sum("credit"), retained_on_cancelled=Sum("retained"))
    entries = FinancialEntry.objects.filter(account__lead__in=filters.base_leads(include_archived=True, dimensions=False))
    if filters.branches:
        entries = entries.filter(branch__in=["" if b == "__unknown__" else b for b in filters.branches])
    for key in ("rto", "source", "campaign", "activity", "sub_activity", "model_interest"):
        if filters.params.get(key):
            entries = entries.filter(**{f"account__lead__{key}": "" if filters.params[key] == "__unknown__" else filters.params[key]})
    entries = filters.period(entries, "occurred_on")
    cash = entries.aggregate(payments=Sum("amount", filter=Q(kind="PAYMENT")), refunds=Sum("amount", filter=Q(kind="REFUND")),
        payment_reversals=Sum("amount", filter=Q(kind="REVERSAL", reverses__kind="PAYMENT")), refund_reversals=Sum("amount", filter=Q(kind="REVERSAL", reverses__kind="REFUND")), net_collections=Sum(signed_amount()))
    retail = filters.milestones().filter(kind="R").aggregate(retail_value=Sum("lead__sale_account__retail_amount"), missing_retail_values=Count("id", filter=Q(lead__sale_account__retail_amount__isnull=True)))
    booked = filters.base_leads().filter(sales_outcome="BOOKED").aggregate(booking_value=Sum("sale_account__agreed_amount"), missing_booking_values=Count("id", filter=Q(sale_account__agreed_amount__isnull=True)))
    return {**{key: value or 0 for key, value in {**balances, **cash}.items()}, **retail, **booked, "currency": "INR"}


def complaint_queryset(filters, period=True):
    qs = Complaint.objects.select_related("assigned_to", "logged_by")
    if filters.branches:
        qs = qs.annotate(_branch=Lower(Trim("branch"))).filter(_branch__in=["" if b == "__unknown__" else b for b in filters.branches])
    if filters.employee:
        qs = qs.filter(Q(assigned_to=filters.employee) | Q(logged_by=filters.employee))
    elif filters.params.get("role"):
        qs = qs.filter(Q(assigned_to__role=filters.params["role"]) | Q(logged_by__role=filters.params["role"]))
    for param, field in (("complaint_status", "status"), ("priority", "priority"), ("complaint_category", "category"), ("subtype", "subtype")):
        if filters.params.get(param):
            qs = qs.filter(**{field: filters.params[param]})
    if filters.params.get("q"):
        q = filters.params["q"]
        qs = qs.filter(Q(customer_name__icontains=q) | Q(customer_phone__icontains=q) | Q(ticket_number__icontains=q) | Q(subject__icontains=q))
    return filters.period(qs, "created_at__date") if period else qs


def complaint_summary(filters):
    qs = complaint_queryset(filters, period=False)
    created = filters.period(qs, "created_at__date")
    resolved = filters.period(qs.filter(resolved_at__isnull=False), "resolved_at__date")
    duration = resolved.filter(resolved_at__gte=F("created_at")).aggregate(value=Avg(ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())))["value"]
    return {"opened": created.count(), "resolved": resolved.count(), "backlog": qs.exclude(status__in=["RESOLVED", "CLOSED"]).count(),
            "escalated": qs.filter(status="ESCALATED").count(), "critical": qs.filter(priority="CRITICAL").exclude(status__in=["RESOLVED", "CLOSED"]).count(),
            "resolution_hours": round(duration.total_seconds() / 3600, 1) if duration is not None else None,
            "by_category": list(created.values("category").annotate(count=Count("id")).order_by("-count"))}


def summary(filters):
    milestones = filters.milestones()
    counts = milestone_counts(milestones)
    cohort = filters.base_leads()
    events = filters.events()
    calls = events.filter(kind="call")
    activity = calls.aggregate(calls=Count("id"), connected=Count("id", filter=Q(after__call_status="Connected")))
    today = timezone.localdate()
    age_queries = {key: Count("id", filter=Q(enquiry_date__lte=today - timedelta(days=low)) & (Q(enquiry_date__gte=today - timedelta(days=high)) if high is not None else Q())) for key, (low, high) in AGE_BANDS.items()}
    ageing = cohort.exclude(status__in=CLOSED).aggregate(**age_queries)
    trend_qs = milestones.exclude(occurred_on__isnull=True)
    monthly = not filters.start or (filters.end - filters.start).days > 62
    trend = list(trend_qs.annotate(date=TruncMonth("occurred_on") if monthly else F("occurred_on")).values("date").annotate(**{kind: Count("lead_id", filter=Q(kind=kind), distinct=True) for kind in KINDS}).order_by("date"))
    if trend:
        by_date = {row["date"]: row for row in trend}
        first, last = trend[0]["date"], trend[-1]["date"]
        if filters.mode == "period" and filters.start:
            first, last = filters.start, filters.end
        if monthly:
            first, last = first.replace(day=1), last.replace(day=1)
        trend = []
        while first <= last:
            trend.append(by_date.get(first, {"date": first, **dict.fromkeys(KINDS, 0)}))
            first = (first.replace(day=28) + timedelta(days=4)).replace(day=1) if monthly else first + timedelta(days=1)
    previous_counts = None
    if filters.start and filters.end:
        previous_end = filters.start - timedelta(days=1)
        previous_start = previous_end - (filters.end - filters.start)
        if filters.range == "mtd":
            previous_start = previous_end.replace(day=1)
            previous_end = previous_end.replace(day=min(filters.end.day, monthrange(previous_end.year, previous_end.month)[1]))
        previous_params = filters.params.copy()
        previous_params.update({"range": "custom", "date_from": previous_start.isoformat(), "date_to": previous_end.isoformat()})
        previous_counts = milestone_counts(ReportFilters(previous_params).milestones())
    return {**filters.metadata(), "ageing": ageing, "trend": trend, "trend_interval": "month" if monthly else "day", "previous_etbr": previous_counts, "etbr": counts, "conversions": conversions(filters), "current": current_counts(cohort),
        "activity": {**activity, "connection_rate": ratio(activity["connected"], calls.exclude(after__call_status="").count()),
                     "cancellations": events.filter(kind="booking_cancelled").count()},
        "finance": financial_summary(filters), "complaints": complaint_summary(filters), "targets": target_summary(filters),
        "coverage": {"unknown_dates": Milestone.objects.filter(lead__in=cohort, occurred_on__isnull=True).count(),
                     "legacy_events": milestones.filter(provenance="legacy").count(),
                     "unknown_branch": milestones.filter(branch="").count(),
                     "unverified_bookings": cohort.filter(sales_outcome__in=["BOOKED", "RETAILED"]).exclude(milestones__kind="B").count(),
                     "unverified_retails": cohort.filter(sales_outcome="RETAILED").exclude(milestones__kind="R").count()}}


def segment_rows(filters, dimension="branch"):
    field = dimension
    qs = filters.milestones()
    if filters.mode == "cohort":
        field = "lead__" + dimension
    qs = qs.annotate(group_key=Lower(Trim(field)) if dimension == "branch" else F(field))
    rows = {row["group_key"] or "": row for row in qs.values("group_key").annotate(
        **{kind: Count("lead_id", filter=Q(kind=kind), distinct=True) for kind in KINDS},
        retail_value=Sum("lead__sale_account__retail_amount", filter=Q(kind="R"))).order_by()}
    current = filters.base_leads().annotate(group_key=Lower(Trim(dimension)) if dimension == "branch" else F(dimension)).values("group_key").annotate(
        current_leads=Count("id", distinct=True), current_booked=Count("id", filter=Q(sales_outcome="BOOKED"), distinct=True),
        current_lost=Count("id", filter=Q(status__in=["LOST", "UNQUALIFIED"]), distinct=True),
        overdue=Count("id", filter=Q(follow_ups__resolved_at__isnull=True, follow_ups__scheduled_for__lt=timezone.now()) & ~Q(status__in=CLOSED), distinct=True))
    labels = branch_options() if dimension == "branch" else {}
    for row in current:
        key = row["group_key"] or ""
        rows.setdefault(key, {"group_key": key, **dict.fromkeys(KINDS, 0), "retail_value": None}).update(row)
    if dimension == "branch":
        for key in labels:
            if not filters.branches or key in filters.branches:
                rows.setdefault(key, {"group_key": key, **dict.fromkeys(KINDS, 0), "retail_value": None})
    # Cohort conversion uses intersection with enquiries for this segment.
    cohort = filters.period(filters.base_leads(), "enquiry_date").annotate(group_key=Lower(Trim(dimension)) if dimension == "branch" else F(dimension))
    rates = {r["group_key"] or "": ratio(r["retails"], r["total"]) for r in cohort.values("group_key").annotate(total=Count("id", distinct=True), retails=Count("id", filter=Q(milestones__kind="R"), distinct=True))}
    for key, row in rows.items():
        row.update(key=key or "__unknown__", label=labels.get(key, key) or "Not recorded", conversion=rates.get(key))
        if dimension == "branch":
            row["targets"] = None  # Populated in one grouped query below.
    if dimension == "branch" and targets_applicable(filters) and not filters.employee and not filters.params.get("role"):
        targets = SalesTarget.objects.filter(month=filters.target_month(), so__isnull=True)
        for item in targets:
            if item.branch in rows:
                rows[item.branch]["targets"] = {key: getattr(item, key) for key in TARGET_FIELDS}
    return sorted(rows.values(), key=lambda row: (-row["E"], row["label"]))


def people_queryset(filters):
    qs = User.objects.filter(role__in=ROLES)
    if filters.params.get("role"):
        qs = qs.filter(role=filters.params["role"])
    if filters.employee:
        qs = qs.filter(pk=filters.employee.pk)
    if filters.branches:
        current = filters.base_leads(employee=False)
        active_ids = filters.events().values("actor_id")
        qs = qs.annotate(_branch=Lower(Trim("location"))).filter(Q(_branch__in=filters.branches) | Q(pk__in=current.values("assigned_so_id")) | Q(pk__in=current.values("assigned_ps_id")) | Q(pk__in=active_ids))
    return qs.order_by("role", "first_name", "email")


def people_rows(filters, users):
    users = list(users)
    ids = [user.pk for user in users]
    workloads = {}
    leads = filters.base_leads(employee=False)
    for field in ("assigned_so_id", "assigned_ps_id"):
        for row in leads.filter(**{field + "__in": ids}).values(field).annotate(assigned=Count("id", distinct=True),
            active=Count("id", filter=~Q(status__in=CLOSED), distinct=True),
            overdue=Count("id", filter=Q(follow_ups__resolved_at__isnull=True, follow_ups__scheduled_for__lt=timezone.now()) & ~Q(status__in=CLOSED), distinct=True),
            qualified=Count("id", filter=Q(status="QUALIFIED"), distinct=True),
            self_generated=Count("id", filter=Q(generated_by_id=F(field)), distinct=True)):
            workloads[row.pop(field)] = row
    activity = {row["actor_id"]: row for row in filters.events().filter(actor_id__in=ids).values("actor_id").annotate(
        calls=Count("id", filter=Q(kind="call")), connected=Count("id", filter=Q(kind="call", after__call_status="Connected")),
        captured=Count("lead_id", filter=Q(kind__in=["created", "imported"]), distinct=True),
        handoffs=Count("id", filter=Q(kind__in=["assigned_ps", "assigned_cre", "reassignment_completed"])),
        last_activity=Max("occurred_at"))}
    milestones = {}
    for role, field in (("CRE", "cre_id"), ("SO", "so_id")):
        for row in filters.milestones().filter(**{field + "__in": ids}).values(field).annotate(**{kind: Count("lead_id", filter=Q(kind=kind), distinct=True) for kind in KINDS}):
            milestones[row.pop(field)] = row
    for row in filters.milestones().filter(lead__milestones__kind="E", lead__milestones__actor_id__in=[u.id for u in users if u.role == "RECEPTIONIST"]).values("lead__milestones__actor_id").annotate(**{kind: Count("lead_id", filter=Q(kind=kind), distinct=True) for kind in KINDS}):
        milestones[row.pop("lead__milestones__actor_id")] = row
    resolved_ids = filters.period(complaint_queryset(filters, False).filter(resolved_at__isnull=False), "resolved_at__date").values("id")
    complaints = {r["assigned_to_id"]: r for r in complaint_queryset(filters, False).filter(assigned_to_id__in=ids).values("assigned_to_id").annotate(
        complaints=Count("id"), open_complaints=Count("id", filter=~Q(status__in=["RESOLVED", "CLOSED"])),
        resolved=Count("id", filter=Q(pk__in=resolved_ids)))}
    targets = {t.so_id: {key: getattr(t, key) for key in TARGET_FIELDS} for t in SalesTarget.objects.filter(month=filters.target_month(), so_id__in=ids)} if targets_applicable(filters) else {}
    branch_results = {row["key"]: row for row in segment_rows(filters)} if any(u.role == "SALES_MANAGER" for u in users) else {}
    result = []
    for user in users:
        row = {"id": user.id, "name": user.history_display_name, "email": user.email, "role": user.role,
            "branch": user.location, "lifecycle": user.lifecycle_status, **dict.fromkeys(["assigned", "active", "overdue", "qualified", "self_generated", "calls", "connected", "captured", "handoffs", "complaints", "open_complaints", "resolved", *KINDS], 0),
            **workloads.get(user.id, {}), **activity.get(user.id, {}), **milestones.get(user.id, {}), **complaints.get(user.id, {}), "targets": targets.get(user.id)}
        if user.role == "SALES_MANAGER":
            row["branch_results"] = branch_results.get(branch_key(user.location))
            branch = row["branch_results"] or {}
            row.update({kind: branch.get(kind, 0) for kind in KINDS})
            row.update(assigned=branch.get("current_leads", 0), overdue=branch.get("overdue", 0), performance_scope="branch")
        else:
            row["performance_scope"] = "captured" if user.role == "RECEPTIONIST" else "complaints" if user.role == "COMPLAINTS" else "assigned"
        result.append(row)
    return result
