import csv
import io
import json

from django.db.models import Count, Max, Min, Q
from django.db.models.functions import Lower, Trim
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsAdmin
from analytics.cache import cache_analytics
from complaints.models import Complaint
from leads.models import Lead, SystemConfig
from leads.rtos import KERALA_RTO_CHOICES
from .filters import DIMENSIONS, ROLES, ReportFilters
from .finance import FinanceInput, TargetInput, save_finance, save_target, target_data
from .models import FinancialEntry, Milestone, OperationEvent, SalesTarget
from .reporting import account_row, branch_options, complaint_queryset, complaint_summary, financial_accounts, financial_summary, people_queryset, people_rows, segment_rows, summary


class CEOReadPermission(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active and request.user.role in {"CEO", "ADMIN"} and request.method in SAFE_METHODS)


class ReportPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class CEOView(APIView):
    permission_classes = [CEOReadPermission]

    def page(self, queryset, request, render=lambda rows: list(rows)):
        pagination = ReportPagination()
        data = render(pagination.paginate_queryset(queryset, request))
        return pagination.get_paginated_response(data)


def lead_sort(params):
    sort = params.get("sort", "-enquiry_date")
    if sort.lstrip("-") not in {"enquiry_date", "name", "status", "branch", "created_at"}:
        raise ValidationError({"sort": "Choose a supported lead sort."})
    return sort


def history_order(queryset, params):
    if params.get("kind"):
        queryset = queryset.filter(kind=params["kind"])
    order = "occurred_at" if params.get("order") == "oldest" else "-occurred_at"
    return queryset.order_by(order, "id" if order == "occurred_at" else "-id")


def lead_rows(queryset):
    ordered_ids = None
    if isinstance(queryset, list):
        ordered_ids = [lead.pk for lead in queryset]
        queryset = Lead.objects.filter(pk__in=ordered_ids)
    queryset = queryset.select_related("assigned_so", "assigned_ps").annotate(
        next_follow_up=Min("follow_ups__scheduled_for", filter=Q(follow_ups__resolved_at__isnull=True)),
        calls=Count("call_logs", distinct=True), last_call=Max("call_logs__created_at"))
    rows = [{"id": lead.id, "name": lead.name, "phone": lead.phone, "branch": lead.branch, "rto": lead.rto,
        "status": lead.status, "sales_outcome": lead.sales_outcome, "source": lead.source, "model": lead.model_interest,
        "category": lead.category, "enquiry_date": lead.enquiry_date, "cre_id": lead.assigned_so_id, "so_id": lead.assigned_ps_id,
        "cre": lead.assigned_so.history_display_name if lead.assigned_so else None,
        "so": lead.assigned_ps.history_display_name if lead.assigned_ps else None,
        "next_follow_up": lead.next_follow_up, "calls": lead.calls, "last_call": lead.last_call} for lead in queryset]
    if ordered_ids is not None:
        positions = {pk: index for index, pk in enumerate(ordered_ids)}
        rows.sort(key=lambda row: positions[row["id"]])
    return rows


def event_row(event):
    return {"id": event.id, "kind": event.kind, "occurred_at": event.occurred_at,
        "actor": event.actor.history_display_name if event.actor else None, "actor_role": event.actor.role if event.actor else None,
        "branch": event.branch, "before": event.before, "after": event.after, "provenance": event.provenance,
        "snapshot": event.snapshot, "lead_id": event.lead_id, "complaint_id": event.complaint_id}


def entry_row(entry):
    return {"id": entry.id, "lead_id": entry.account.lead_id, "kind": entry.kind, "amount": entry.amount,
        "occurred_on": entry.occurred_on, "method": entry.method, "reference": entry.reference,
        "notes": entry.notes, "reverses": entry.reverses_id, "reversed": hasattr(entry, "reversal"),
        "actor": entry.actor.history_display_name, "before": entry.before,
        "after": {key: value for key, value in entry.after.items() if key != "request"}, "created_at": entry.created_at}


class CEOOptionsView(CEOView):
    def get(self, request):
        branches = branch_options()
        lists = (SystemConfig.objects.filter(pk=1).values_list("lists", flat=True).first() or {})
        options = {key: sorted(set(Lead.objects.exclude(**{key: ""}).values_list(key, flat=True))) for key in DIMENSIONS if key not in {"rto", "activity", "sub_activity"}}
        users = User.objects.filter(role__in=ROLES).order_by("first_name", "email")
        return Response({"branches": [{"value": key, "label": value} for key, value in sorted(branches.items())] + [{"value": "__unknown__", "label": "Not recorded"}],
            "employees": [{"id": u.id, "name": u.history_display_name, "role": u.role, "branch": u.location.strip().casefold(), "lifecycle": u.lifecycle_status} for u in users],
            "roles": [{"value": value, "label": label} for value, label in User.Role.choices if value in ROLES],
            "rtos": [{"value": code, "label": f"{code} · {name}"} for code, name in KERALA_RTO_CHOICES],
            "statuses": [{"value": value, "label": label} for value, label in Lead.Status.choices],
            "activities": lists.get("activities", []), "sub_activities": lists.get("subActivities", {}), **options})


class CEOReportView(CEOView):
    @cache_analytics("ceo-report", max_ttl=60)
    def get(self, request, section="overview"):
        filters = ReportFilters(request.query_params)
        if section == "overview":
            payload = summary(filters)
            payload["branches"] = segment_rows(filters)
            return Response(payload)
        if section == "branches":
            return Response({**filters.metadata(), "results": segment_rows(filters)})
        if section == "segments":
            dimension = request.query_params.get("dimension", "rto")
            if dimension not in DIMENSIONS:
                raise ValidationError({"dimension": "Choose RTO, source, campaign, activity, sub-activity or model."})
            return self.page(segment_rows(filters, dimension), request)
        if section == "people":
            return self.page(people_queryset(filters), request, lambda rows: people_rows(filters, rows))
        if section == "leads":
            return self.page(filters.leads().order_by(lead_sort(request.query_params), "-id"), request, lead_rows)
        if section == "finance":
            page = self.page(financial_accounts(filters).order_by("-updated_at"), request, lambda rows: [account_row(row) for row in rows])
            page.data["summary"] = financial_summary(filters)
            return page
        if section == "complaints":
            from complaints.serializers import ComplaintListSerializer
            qs = complaint_queryset(filters, period=request.query_params.get("scope") != "workload").annotate(_note_count=Count("notes"))
            page = self.page(qs.order_by("-created_at"), request, lambda rows: ComplaintListSerializer(rows, many=True).data)
            page.data["summary"] = complaint_summary(filters)
            return page
        raise ValidationError({"section": "Unknown CEO report."})


class CEOLeadDetailView(CEOView):
    def get(self, request, pk):
        lead = get_object_or_404(Lead.objects.select_related("assigned_so", "assigned_ps", "qualification"), pk=pk)
        # Histories are separate and paginated; do not load them through the
        # older detail serializer's unbounded call/follow-up lists.
        from leads.serializers import LeadSerializer
        record = LeadSerializer(lead).data
        record["milestones"] = list(lead.milestones.values("kind", "occurred_on", "occurred_at", "branch", "provenance", "actor_id", "cre_id", "so_id"))
        record["archived"] = bool(lead.deleted_at)
        record["related_complaints"] = list(lead.complaints.values("id", "ticket_number", "subject", "status"))
        record["finance"] = next((account_row(account) for account in financial_accounts(ReportFilters(request.query_params)).filter(lead=lead)), None)
        return Response(record)


class CEOHistoryView(CEOView):
    def get(self, request, pk, entity="leads"):
        if entity == "leads":
            get_object_or_404(Lead, pk=pk)
            queryset = OperationEvent.objects.filter(lead_id=pk)
        elif entity == "complaints":
            get_object_or_404(Complaint, pk=pk)
            queryset = OperationEvent.objects.filter(complaint_id=pk)
        else:
            raise ValidationError({"entity": "Unknown record type."})
        return self.page(history_order(queryset.select_related("actor"), request.query_params), request, lambda rows: [event_row(e) for e in rows])


class CEOComplaintDetailView(CEOView):
    def get(self, request, pk):
        from complaints.serializers import ComplaintListSerializer
        complaint = get_object_or_404(Complaint.objects.select_related("assigned_to", "logged_by").annotate(_note_count=Count("notes")), pk=pk)
        return Response({**ComplaintListSerializer(complaint).data, "related_lead": complaint.related_lead_id})


class TargetMaintenanceView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = SalesTarget.objects.select_related("so").order_by("-month", "branch", "so_id")
        if request.query_params.get("month"):
            field = serializers.DateField()
            qs = qs.filter(month=field.run_validation(request.query_params["month"]))
        if request.query_params.get("branch"):
            qs = qs.filter(branch=request.query_params["branch"].strip().casefold())
        paginator = ReportPagination()
        return paginator.get_paginated_response([target_data(t) for t in paginator.paginate_queryset(qs, request)])

    def post(self, request):
        serializer = TargetInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(target_data(save_target(serializer.validated_data, request.user)))


class TargetHistoryView(CEOView):
    def get(self, request, pk):
        target = get_object_or_404(SalesTarget, pk=pk)
        return self.page(target.revisions.select_related("actor").order_by("-created_at"), request,
            lambda rows: [{"id": r.id, "actor": r.actor.history_display_name, "before": r.before, "after": r.after, "created_at": r.created_at} for r in rows])


class FinanceMaintenanceView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = FinanceInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = save_finance(serializer.validated_data, request.user)
        return Response(entry_row(entry))


class FinanceEntriesView(CEOView):
    def get(self, request, pk):
        queryset = FinancialEntry.objects.filter(account__lead_id=pk).select_related("actor", "account", "reversal")
        return self.page(queryset, request, lambda rows: [entry_row(row) for row in rows])


def csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, default=str)
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


class CEOExportView(CEOView):
    def get(self, request, section):
        filters = ReportFilters(request.query_params)
        if section == "leads":
            queryset = filters.leads().order_by(lead_sort(request.query_params), "-id")
            def lead_export():
                for offset in range(0, queryset.count(), 500):
                    yield from lead_rows(queryset[offset:offset + 500])
            rows = lead_export()
        elif section in {"branches", "segments"}:
            dimension = "branch" if section == "branches" else request.query_params.get("dimension", "rto")
            if dimension not in ("branch", *DIMENSIONS):
                raise ValidationError({"dimension": "Unknown dimension."})
            rows = iter(segment_rows(filters, dimension))
        elif section == "people":
            queryset = people_queryset(filters)
            def people_export():
                for offset in range(0, queryset.count(), 100):
                    yield from people_rows(filters, queryset[offset:offset + 100])
            rows = people_export()
        elif section == "finance":
            rows = (account_row(row) for row in financial_accounts(filters).order_by("-updated_at").iterator(chunk_size=500))
        elif section == "complaints":
            rows = complaint_queryset(filters, request.query_params.get("scope") != "workload").values("id", "ticket_number", "customer_name", "customer_phone", "branch", "status", "priority", "category", "subtype", "assigned_to_id", "logged_by_id", "created_at", "resolved_at").iterator(chunk_size=500)
        elif section == "history":
            pk = request.query_params.get("lead")
            if not pk or not pk.isdigit():
                raise ValidationError({"lead": "Choose a lead to export its history."})
            get_object_or_404(Lead, pk=pk)
            rows = (event_row(row) for row in history_order(OperationEvent.objects.filter(lead_id=pk).select_related("actor"), request.query_params).iterator(chunk_size=500))
        else:
            payload = summary(filters) if section == "overview" else None
            if payload is None:
                raise ValidationError({"section": "Unknown export."})
            rows = iter({"section": key, "values": value} for key, value in payload.items())
        def stream():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            def line(values):
                buffer.seek(0)
                buffer.truncate(0)
                writer.writerow([csv_cell(v) for v in values])
                return buffer.getvalue()
            yield "\ufeff"
            yield line(["CEO report", section, "Generated", timezone.now().isoformat()])
            yield line(["Filters", dict(request.query_params.lists()), "Timezone", "Asia/Kolkata"])
            columns = None
            for row in rows:
                if columns is None:
                    columns = list(row)
                    yield line(columns)
                yield line([row.get(column) for column in columns])
        response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="ceo-{section}-{timezone.localdate()}.csv"'
        return response
