from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Min, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsAdmin, IsAdminOrReceptionist, IsAdminReceptionistOrCRE, IsSalesManager
from notifications.models import Notification
from .models import CallLog, FollowUp, Lead, LeadAudit, LeadQualification, SystemConfig
from .serializers import CALL_OUTCOME_STATUS_OPTIONS, PS_CALL_OUTCOME_STATUS_OPTIONS, AssignmentSerializer, BulkDistributeSerializer, FollowUpSerializer, LeadDetailSerializer, LeadSerializer, LeadUpdateSerializer, PSAssignmentSerializer, SOLeadListSerializer, SOLeadUpdateSerializer, SystemConfigSerializer

FORWARD_TRANSITIONS = {
    Lead.Status.FRESH: {Lead.Status.RNR, Lead.Status.SWITCHED_OFF, Lead.Status.CALLBACK, Lead.Status.PENDING, Lead.Status.QUALIFIED, Lead.Status.UNQUALIFIED, Lead.Status.LOST},
    Lead.Status.RNR: {Lead.Status.RNR, Lead.Status.SWITCHED_OFF, Lead.Status.CALLBACK, Lead.Status.PENDING, Lead.Status.QUALIFIED, Lead.Status.UNQUALIFIED, Lead.Status.LOST},
    Lead.Status.SWITCHED_OFF: {Lead.Status.RNR, Lead.Status.SWITCHED_OFF, Lead.Status.CALLBACK, Lead.Status.PENDING, Lead.Status.QUALIFIED, Lead.Status.UNQUALIFIED, Lead.Status.LOST},
    Lead.Status.CALLBACK: {Lead.Status.RNR, Lead.Status.SWITCHED_OFF, Lead.Status.PENDING, Lead.Status.QUALIFIED, Lead.Status.UNQUALIFIED, Lead.Status.WALKIN, Lead.Status.LOST},
    Lead.Status.PENDING: {Lead.Status.RNR, Lead.Status.SWITCHED_OFF, Lead.Status.CALLBACK, Lead.Status.PENDING, Lead.Status.QUALIFIED, Lead.Status.UNQUALIFIED, Lead.Status.WALKIN, Lead.Status.LOST},
    Lead.Status.QUALIFIED: {Lead.Status.WALKIN, Lead.Status.WON, Lead.Status.LOST},
    Lead.Status.WALKIN: {Lead.Status.WON, Lead.Status.LOST},
}

def apply_lead_filters(queryset, filters):
    if value := filters.get("source"):
        queryset = queryset.filter(source=value)
    if value := filters.get("status"):
        queryset = queryset.filter(status=value)
    if value := filters.get("sales_outcome"):
        queryset = queryset.filter(sales_outcome=value)
    for key, field in (("model", "model_interest"), ("city", "city"), ("campaign", "campaign")):
        if value := filters.get(key):
            queryset = queryset.filter(**{f"{field}__icontains": value})
    if value := filters.get("source_label"):
        queryset = queryset.filter(Q(source_label__icontains=value) | Q(campaign__icontains=value))
    if value := filters.get("q"):
        queryset = queryset.filter(Q(name__icontains=value) | Q(phone__icontains=value) | Q(campaign__icontains=value) | Q(model_interest__icontains=value) | Q(source_label__icontains=value))
    for key, lookup in (("date_from", "enquiry_date__gte"), ("date_to", "enquiry_date__lte")):
        if value := filters.get(key):
            parsed = parse_date(str(value))
            if not parsed:
                raise ValidationError({key: "Use YYYY-MM-DD."})
            queryset = queryset.filter(**{lookup: parsed})
    return queryset


def audit_value(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


class LeadViewSet(viewsets.ModelViewSet):
    serializer_class = LeadSerializer

    def get_queryset(self):
        queryset = Lead.objects.filter(deleted_at__isnull=True).select_related("assigned_so", "assigned_ps", "qualification").annotate(
            _call_count=Count("call_logs", distinct=True),
            _next_follow_up=Min("follow_ups__scheduled_for", filter=Q(follow_ups__resolved_at__isnull=True)),
        )
        if not self.request.user.is_admin and self.request.user.role == User.Role.CRE:
            queryset = queryset.filter(assigned_so=self.request.user)
        elif not self.request.user.is_admin and self.request.user.role == User.Role.SALES_MANAGER:
            queryset = queryset.filter(branch__iexact=self.request.user.location.strip()) if self.request.user.location.strip() else queryset.none()
        elif not self.request.user.is_admin:
            queryset = queryset.filter(assigned_ps=self.request.user)
        elif self.request.query_params.get("unassigned") == "true":
            queryset = queryset.filter(assigned_so__isnull=True)
        elif self.request.query_params.get("ps_unassigned") == "true":
            queryset = queryset.filter(status=Lead.Status.QUALIFIED, assigned_ps__isnull=True)
        if value := self.request.query_params.get("assigned_so"):
            queryset = queryset.filter(assigned_so=value)
        if value := self.request.query_params.get("assigned_ps"):
            queryset = queryset.filter(assigned_ps=value)
        queryset = apply_lead_filters(queryset, self.request.query_params)
        ordering = self.request.query_params.get("ordering", "-created_at")
        return queryset.order_by(ordering if ordering.lstrip("-") in {"created_at", "enquiry_date", "status"} else "-created_at")

    def retrieve(self, request, *args, **kwargs):
        return Response(LeadDetailSerializer(self.get_object()).data)

    def perform_create(self, serializer):
        is_walkin = (
            serializer.validated_data.get("source") == Lead.Source.WALKIN
            or serializer.validated_data.get("status") == Lead.Status.WALKIN
        )
        if is_walkin:
            # Walk-in leads bypass CRE – go directly to PS/SO as qualified
            lead = serializer.save(status=Lead.Status.QUALIFIED)
        elif not self.request.user.is_admin and getattr(self.request.user, "role", None) == User.Role.CRE:
            lead = serializer.save(assigned_so=self.request.user)
        else:
            lead = serializer.save()
        LeadAudit.objects.create(lead=lead, actor=self.request.user, event="created")

    def get_permissions(self):
        if getattr(self.request.user, "role", None) == User.Role.SALES_MANAGER and self.request.method not in SAFE_METHODS:
            return [IsAdmin()]
        if self.action in {"assign", "assign_ps", "bulk_assign", "bulk_assign_ps", "bulk_distribute", "auto_assign", "reopen", "destroy"}:
            return [IsAdmin()]
        if self.action == "create":
            return [IsAdminReceptionistOrCRE()]
        return super().get_permissions()

    @action(detail=False, methods=["get"], url_path="manager-leads", permission_classes=[IsSalesManager])
    def manager_leads(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        if value := request.query_params.get("cre"):
            queryset = queryset.filter(assigned_so_id=value)
        if value := request.query_params.get("ps"):
            queryset = queryset.filter(assigned_ps_id=value)
        if request.query_params.get("flagged") == "true":
            queryset = queryset.filter(flagged_to_manager=True)
        if request.query_params.get("followup") == "overdue":
            queryset = queryset.filter(follow_ups__resolved_at__isnull=True, follow_ups__scheduled_for__lt=timezone.now()).distinct()
        if request.query_params.get("risk") == "stale":
            queryset = queryset.filter(status=Lead.Status.FRESH, created_at__date__lte=timezone.localdate() - timedelta(days=3))
        if request.query_params.get("status_group") == "lost_or_unqualified":
            queryset = queryset.filter(status__in=[Lead.Status.LOST, Lead.Status.UNQUALIFIED])
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="my-dashboard")
    def my_dashboard(self, request):
        today = timezone.localdate()
        is_cre = request.user.role == User.Role.CRE
        owner_filter = {"assigned_so": request.user} if is_cre else {"assigned_ps": request.user}
        queryset = Lead.objects.filter(deleted_at__isnull=True, **owner_filter)
        open_followup = Q(follow_ups__id__isnull=False, follow_ups__resolved_at__isnull=True)
        due_followup = open_followup & Q(follow_ups__scheduled_for__date__lte=today)
        followup_filter = due_followup
        if is_cre:
            followup_filter = due_followup & Q(status=Lead.Status.PENDING, call_logs__outcome="Call Me Back")
        pending_status = Q(status__in=[Lead.Status.RNR, Lead.Status.SWITCHED_OFF, Lead.Status.PENDING])
        called_status = Q(status__in=[Lead.Status.RNR, Lead.Status.SWITCHED_OFF])
        date_range = request.query_params.get("range", "all")
        if date_range == "today":
            queryset = queryset.filter(enquiry_date=today)
        elif date_range == "mtd":
            queryset = queryset.filter(enquiry_date__year=today.year, enquiry_date__month=today.month)
        elif request.query_params.get("date_from") or request.query_params.get("date_to"):
            if request.query_params.get("date_from"):
                queryset = queryset.filter(enquiry_date__gte=parse_date(request.query_params["date_from"]))
            if request.query_params.get("date_to"):
                queryset = queryset.filter(enquiry_date__lte=parse_date(request.query_params["date_to"]))

        pending_queryset = queryset.filter(pending_status)
        if is_cre:
            pending_queryset = pending_queryset.exclude(followup_filter)
        fresh_queryset = queryset.filter(status=Lead.Status.FRESH) if is_cre else queryset.filter(status=Lead.Status.QUALIFIED).exclude(call_logs__so=request.user)

        pending_filter = pending_status & (~followup_filter if is_cre else Q())
        fresh_filter = Q(status=Lead.Status.FRESH) if is_cre else Q(status=Lead.Status.QUALIFIED) & ~Q(call_logs__so=request.user)
        summary = queryset.aggregate(
            total=Count("id", distinct=True),
            fresh=Count("id", filter=fresh_filter, distinct=True),
            followups=Count("id", filter=followup_filter, distinct=True),
            pending=Count("id", filter=pending_filter, distinct=True),
            qualified=Count("id", filter=Q(status=Lead.Status.QUALIFIED), distinct=True),
            walkin=Count("id", filter=Q(status=Lead.Status.WALKIN), distinct=True),
            won=Count("id", filter=Q(status=Lead.Status.WON), distinct=True),
            lost=Count("id", filter=Q(status__in=[Lead.Status.LOST, Lead.Status.UNQUALIFIED]), distinct=True),
            won_lost=Count("id", filter=Q(status__in=[Lead.Status.WON, Lead.Status.LOST, Lead.Status.UNQUALIFIED]), distinct=True),
            untouched=Count("id", filter=Q(status=Lead.Status.FRESH), distinct=True),
            called=Count("id", filter=called_status, distinct=True),
            scheduled=Count("id", filter=open_followup, distinct=True),
        )
        section = request.query_params.get("section", "fresh")
        fresh_subfilter = request.query_params.get("subfilter", "untouched")
        fresh_filters = {
            "untouched": Q(status=Lead.Status.FRESH),
            "called": called_status,
            "scheduled": open_followup,
        }
        section_filters = {
            "all": Q(),
            "fresh": Q(status=Lead.Status.FRESH),
            "followups": followup_filter,
            "pending": pending_status,
            "qualified": Q(status=Lead.Status.QUALIFIED),
            "walkin": Q(status=Lead.Status.WALKIN),
            "won": Q(status=Lead.Status.WON),
            "lost": Q(status__in=[Lead.Status.LOST, Lead.Status.UNQUALIFIED]),
            "won_lost": Q(status__in=[Lead.Status.WON, Lead.Status.LOST, Lead.Status.UNQUALIFIED]),
            "active": ~Q(status__in=[Lead.Status.WON, Lead.Status.LOST, Lead.Status.UNQUALIFIED]),
        }
        if section == "fresh":
            queryset = queryset.filter(fresh_filters[fresh_subfilter]) if is_cre and fresh_subfilter in fresh_filters else fresh_queryset
        elif section == "pending" and is_cre:
            queryset = pending_queryset
        elif section in section_filters:
            queryset = queryset.filter(section_filters[section])
        if value := request.query_params.get("category"):
            queryset = queryset.filter(category=value.upper())
        if value := request.query_params.get("source"):
            queryset = queryset.filter(source=value.upper())
        if value := request.query_params.get("q"):
            queryset = queryset.filter(Q(name__icontains=value) | Q(phone__icontains=value) | Q(campaign__icontains=value) | Q(model_interest__icontains=value) | Q(branch__icontains=value))
        leads = queryset.distinct().order_by("-enquiry_date", "-created_at").only("id", "status", "name", "phone", "source", "flagged_to_manager")
        return Response({"summary": summary, "section": section, "results": SOLeadListSerializer(leads, many=True).data})

    @action(detail=True, methods=["patch"], url_path="so-update")
    def so_update(self, request, pk=None):
        lead = self.get_object()
        user_field = "assigned_so_id" if request.user.role == User.Role.CRE else "assigned_ps_id"
        if not request.user.is_admin and getattr(lead, user_field) != request.user.id:
            return Response({"detail": "This lead is not assigned to you."}, status=status.HTTP_403_FORBIDDEN)
        serializer = SOLeadUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sales_status = {Lead.SalesOutcome.BOOKED: Lead.Status.WALKIN, Lead.SalesOutcome.RETAILED: Lead.Status.WON, Lead.SalesOutcome.LOST: Lead.Status.LOST}
        call_status = {"QUALIFIED": Lead.Status.QUALIFIED, "PENDING": Lead.Status.PENDING, "LOST": Lead.Status.LOST, "RNR": Lead.Status.RNR, "SWITCHED_OFF": Lead.Status.SWITCHED_OFF, "CALLBACK": Lead.Status.CALLBACK}
        call_outcome = data.get("call_outcome")
        if call_outcome in CALL_OUTCOME_STATUS_OPTIONS:
            next_status = data.get("status") or {"PENDING": Lead.Status.PENDING, "QUALIFIED": Lead.Status.QUALIFIED, "LOST": Lead.Status.LOST, "RNR": Lead.Status.RNR, "SWITCHED_OFF": Lead.Status.SWITCHED_OFF, "CALLBACK": Lead.Status.CALLBACK}.get(call_outcome)
            if next_status not in CALL_OUTCOME_STATUS_OPTIONS[call_outcome]:
                return Response({"detail": "Choose a lead status that matches the call outcome."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            next_status = call_status.get(call_outcome) if call_outcome else data.get("status") or sales_status.get(data.get("sales_outcome"), lead.status)
        if request.user.role == User.Role.SALES_OFFICER and data.get("call_status") == "Not Connected" and call_outcome == "Call Me Back":
            return Response({"detail": "Call Me Back requires a connected call."}, status=status.HTTP_400_BAD_REQUEST)
        if call_outcome == "PENDING" and not data.get("follow_up_at"):
            return Response({"detail": "Pending calls require a follow-up time."}, status=status.HTTP_400_BAD_REQUEST)
        follow_up_statuses = {Lead.Status.RNR, Lead.Status.SWITCHED_OFF, Lead.Status.CALLBACK, Lead.Status.PENDING, Lead.Status.WALKIN}
        if call_outcome in CALL_OUTCOME_STATUS_OPTIONS and next_status not in follow_up_statuses and data.get("follow_up_at"):
            return Response({"detail": "This outcome cannot have a follow-up time."}, status=status.HTTP_400_BAD_REQUEST)
        if call_outcome and call_outcome not in CALL_OUTCOME_STATUS_OPTIONS and call_outcome != "PENDING" and data.get("follow_up_at"):
            return Response({"detail": "Only pending calls can have a follow-up time."}, status=status.HTTP_400_BAD_REQUEST)
        if data.get("follow_up_at") and next_status == Lead.Status.FRESH:
            next_status = Lead.Status.CALLBACK
        if data.get("follow_up_at") and next_status not in follow_up_statuses:
            return Response({"detail": "Only callbacks and walk-ins can have an appointment."}, status=status.HTTP_400_BAD_REQUEST)
        if request.user.role == User.Role.CRE and lead.status == Lead.Status.QUALIFIED and next_status == Lead.Status.QUALIFIED and (call_outcome == "QUALIFIED" or data.get("qualification")):
            return Response({"detail": "This lead is already qualified."}, status=status.HTTP_400_BAD_REQUEST)
        ps_officer = data.get("ps_officer")
        qualification_update = (
            request.user.role == User.Role.CRE
            and next_status == Lead.Status.QUALIFIED
            and (
                lead.status != Lead.Status.QUALIFIED
                or call_outcome == "QUALIFIED"
                or ps_officer
                or "city" in data
                or data.get("qualification")
            )
        )
        if not request.user.is_admin and qualification_update:
            location = (data.get("city") or lead.city or "").strip()
            if not location:
                return Response({"city": "Select customer location before qualifying this lead."}, status=status.HTTP_400_BAD_REQUEST)
            assigned_ps = ps_officer or lead.assigned_ps
            if not assigned_ps:
                return Response({"ps_officer_id": "Choose the PS/SO for this customer location."}, status=status.HTTP_400_BAD_REQUEST)
            if assigned_ps.location.strip().lower() != location.lower():
                return Response({"ps_officer_id": "Choose a PS/SO assigned to this customer location."}, status=status.HTTP_400_BAD_REQUEST)
        ps_outcome = request.user.role == User.Role.SALES_OFFICER and lead.status not in {Lead.Status.WON, Lead.Status.LOST, Lead.Status.UNQUALIFIED} and call_outcome in PS_CALL_OUTCOME_STATUS_OPTIONS
        if not request.user.is_admin and not ps_outcome and next_status != lead.status and next_status not in FORWARD_TRANSITIONS.get(lead.status, set()):
            return Response({"detail": "This status transition is not allowed."}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.is_admin and request.user.role == User.Role.SALES_OFFICER and data.get("qualification"):
            return Response({"detail": "PS/SO users cannot edit CRE qualification details."}, status=status.HTTP_403_FORBIDDEN)
        editable_fields = ("name", "phone", "email", "source", "source_label", "campaign", "model_interest", "city", "branch", "enquiry_date", "flagged_to_manager")
        before = {field: audit_value(getattr(lead, field)) for field in ("status", "category", "sales_outcome", *editable_fields)}
        with transaction.atomic():
            lead.status = next_status
            for field in ("category", "sales_outcome", *editable_fields):
                if field in data:
                    setattr(lead, field, data[field])
            update_fields = ["status", "category", "sales_outcome", *[field for field in editable_fields if field in data], "updated_at"]
            if ps_officer and request.user.role == User.Role.CRE:
                lead.assigned_ps = ps_officer
                update_fields.append("assigned_ps")
            lead.save(update_fields=update_fields)
            if qualification := data.get("qualification"):
                record, _ = LeadQualification.objects.get_or_create(lead=lead)
                for field, value in qualification.items():
                    setattr(record, field, value)
                record.updated_by = request.user
                record.save()
            if any(field in data for field in ("status", "sales_outcome", "remarks", "call_status", "call_outcome", "follow_up_at")):
                FollowUp.objects.filter(lead=lead, resolved_at__isnull=True).update(resolved_at=timezone.now())
                CallLog.objects.create(lead=lead, so=request.user, status=next_status, call_status=data.get("call_status", ""), outcome=data.get("call_outcome", ""), remarks=data.get("remarks", ""))
                if follow_up_at := data.get("follow_up_at"):
                    FollowUp.objects.create(lead=lead, so=request.user, scheduled_for=follow_up_at)
            after = {field: audit_value(getattr(lead, field)) for field in ("status", "category", "sales_outcome", *editable_fields)}
            LeadAudit.objects.create(lead=lead, actor=request.user, event="so_updated", before=before, after=after)
            if ps_officer and request.user.role == User.Role.CRE:
                LeadAudit.objects.create(lead=lead, actor=request.user, event="assigned_ps", after={"assigned_ps": ps_officer.id})
                Notification.objects.create(user=ps_officer, lead=lead, kind=Notification.Kind.ASSIGNMENT, message=f"You have a qualified lead: {lead.name}.")
        return Response(LeadDetailSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        lead = self.get_object()
        serializer = AssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        officer = serializer.validated_data["sales_officer"]
        with transaction.atomic():
            lead = Lead.objects.select_for_update().get(pk=lead.pk)
            if lead.assigned_so_id:
                return Response({"detail": "This lead is already assigned."}, status=status.HTTP_409_CONFLICT)
            lead.assigned_so = officer
            lead.save(update_fields=["assigned_so", "updated_at"])
            LeadAudit.objects.create(lead=lead, actor=request.user, event="assigned_cre", after={"assigned_so": officer.id})
            Notification.objects.create(user=officer, lead=lead, kind=Notification.Kind.ASSIGNMENT, message=f"You have a new lead: {lead.name}.")
        return Response(self.get_serializer(lead).data)

    @action(detail=True, methods=["post"], url_path="assign-ps")
    def assign_ps(self, request, pk=None):
        lead = self.get_object()
        serializer = PSAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        officer = serializer.validated_data["sales_officer"]
        with transaction.atomic():
            lead = Lead.objects.select_for_update().get(pk=lead.pk)
            if lead.status != Lead.Status.QUALIFIED:
                return Response({"detail": "Only qualified leads can be assigned to PS/SO."}, status=status.HTTP_400_BAD_REQUEST)
            if lead.assigned_ps_id:
                return Response({"detail": "This lead is already assigned to PS/SO."}, status=status.HTTP_409_CONFLICT)
            lead.assigned_ps = officer
            lead.save(update_fields=["assigned_ps", "updated_at"])
            LeadAudit.objects.create(lead=lead, actor=request.user, event="assigned_ps", after={"assigned_ps": officer.id})
            Notification.objects.create(user=officer, lead=lead, kind=Notification.Kind.ASSIGNMENT, message=f"You have a qualified lead: {lead.name}.")
        return Response(self.get_serializer(lead).data)

    @action(detail=False, methods=["post"], url_path="bulk-assign")
    def bulk_assign(self, request):
        serializer = AssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        filters = request.data.get("filters", {})
        if not isinstance(filters, dict):
            raise ValidationError({"filters": "Expected an object of filter values."})
        officer = serializer.validated_data["sales_officer"]
        leads = Lead.objects.filter(deleted_at__isnull=True, assigned_so__isnull=True, assigned_ps__isnull=True)
        leads = apply_lead_filters(leads, filters)
        with transaction.atomic():
            leads = list(leads.select_for_update().order_by("created_at"))
            now = timezone.now()
            for lead in leads:
                lead.assigned_so = officer
                lead.updated_at = now
            if leads:
                Lead.objects.bulk_update(leads, fields=["assigned_so", "updated_at"], batch_size=1000)
            LeadAudit.objects.bulk_create([LeadAudit(lead=lead, actor=request.user, event="assigned_cre", after={"assigned_so": officer.id}) for lead in leads])
            if leads:
                Notification.objects.create(user=officer, kind=Notification.Kind.ASSIGNMENT, message=f"You have {len(leads)} new lead(s) assigned.")
        return Response({"assigned": len(leads)})

    @action(detail=False, methods=["post"], url_path="bulk-assign-ps")
    def bulk_assign_ps(self, request):
        serializer = PSAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        filters = request.data.get("filters", {})
        if not isinstance(filters, dict):
            raise ValidationError({"filters": "Expected an object of filter values."})
        officer = serializer.validated_data["sales_officer"]
        leads = Lead.objects.filter(deleted_at__isnull=True, status=Lead.Status.QUALIFIED, assigned_ps__isnull=True)
        leads = apply_lead_filters(leads, filters)
        with transaction.atomic():
            leads = list(leads.select_for_update().order_by("created_at"))
            now = timezone.now()
            for lead in leads:
                lead.assigned_ps = officer
                lead.updated_at = now
            if leads:
                Lead.objects.bulk_update(leads, fields=["assigned_ps", "updated_at"], batch_size=1000)
            LeadAudit.objects.bulk_create([LeadAudit(lead=lead, actor=request.user, event="assigned_ps", after={"assigned_ps": officer.id}) for lead in leads])
            if leads:
                Notification.objects.create(user=officer, kind=Notification.Kind.ASSIGNMENT, message=f"You have {len(leads)} qualified lead(s) assigned.")
        return Response({"assigned": len(leads)})

    @action(detail=False, methods=["post"], url_path="bulk-distribute")
    def bulk_distribute(self, request):
        serializer = BulkDistributeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        filters = request.data.get("filters", {})
        if not isinstance(filters, dict):
            raise ValidationError({"filters": "Expected an object of filter values."})
        officers = serializer.validated_data["sales_officer_ids"]
        leads = Lead.objects.filter(deleted_at__isnull=True, assigned_so__isnull=True, assigned_ps__isnull=True)
        leads = apply_lead_filters(leads, filters)
        with transaction.atomic():
            leads = list(leads.select_for_update().order_by("created_at"))
            distribution = defaultdict(int)
            audits = []
            now = timezone.now()
            for index, lead in enumerate(leads):
                officer = officers[index % len(officers)]
                lead.assigned_so = officer
                lead.updated_at = now
                distribution[officer.id] += 1
                audits.append(LeadAudit(lead=lead, actor=request.user, event="bucket_assigned_cre", after={"assigned_so": officer.id}))
            if leads:
                Lead.objects.bulk_update(leads, fields=["assigned_so", "updated_at"], batch_size=1000)
                LeadAudit.objects.bulk_create(audits)
                Notification.objects.bulk_create([Notification(user=officer, kind=Notification.Kind.ASSIGNMENT, message=f"You have {distribution[officer.id]} new lead(s) assigned.") for officer in officers if distribution[officer.id]])
        return Response({"assigned": len(leads), "distribution": [{"sales_officer_id": officer.id, "name": officer.get_full_name() or officer.email, "assigned": distribution[officer.id]} for officer in officers]})

    @action(detail=False, methods=["post"], url_path="auto-assign")
    def auto_assign(self, request):
        lead_ids = request.data.get("lead_ids", [])
        with transaction.atomic():
            leads = Lead.objects.select_for_update().filter(deleted_at__isnull=True, assigned_so__isnull=True, assigned_ps__isnull=True)
            if lead_ids:
                leads = leads.filter(id__in=lead_ids)
            leads = list(leads.order_by("created_at"))
            officers = list(User.objects.filter(role=User.Role.CRE, is_active=True).annotate(load=Count("assigned_leads", filter=Q(assigned_leads__deleted_at__isnull=True))).order_by("load", "id"))
            if not officers:
                return Response({"detail": "No active CRE users."}, status=status.HTTP_400_BAD_REQUEST)
            if not leads:
                return Response({"assigned": 0, "distribution": {}})
            distribution = defaultdict(int)
            audits = []
            now = timezone.now()
            for index, lead in enumerate(leads):
                officer = officers[index % len(officers)]
                lead.assigned_so = officer
                lead.updated_at = now
                audits.append(LeadAudit(lead=lead, actor=request.user, event="auto_assigned_cre", after={"assigned_so": officer.id}))
                distribution[officer.get_full_name() or officer.email] += 1
            if leads:
                Lead.objects.bulk_update(leads, fields=["assigned_so", "updated_at"], batch_size=1000)
                LeadAudit.objects.bulk_create(audits)
            Notification.objects.bulk_create([Notification(user=officer, kind=Notification.Kind.ASSIGNMENT, message=f"You have {count} new lead(s) assigned.") for officer, count in ((officer, distribution.get(officer.get_full_name() or officer.email, 0)) for officer in officers) if count])
        return Response({"assigned": len(leads), "distribution": distribution})

    @action(detail=True, methods=["post"], url_path="log-call")
    def log_call(self, request, pk=None):
        with transaction.atomic():
            lead = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            user_field = "assigned_so_id" if request.user.role == User.Role.CRE else "assigned_ps_id"
            if not request.user.is_admin and getattr(lead, user_field) != request.user.id:
                return Response({"detail": "This lead is not assigned to you."}, status=status.HTTP_403_FORBIDDEN)
            serializer = LeadUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            next_status = serializer.validated_data["status"]
            if next_status not in FORWARD_TRANSITIONS.get(lead.status, set()):
                return Response({"detail": "This status transition is not allowed."}, status=status.HTTP_400_BAD_REQUEST)
            previous = lead.status
            lead.status = next_status
            lead.save(update_fields=["status", "updated_at"])
            CallLog.objects.create(lead=lead, so=request.user, status=next_status, call_status=serializer.validated_data.get("call_status", ""), outcome=serializer.validated_data.get("call_outcome", ""), remarks=serializer.validated_data.get("remarks", ""))
            FollowUp.objects.filter(lead=lead, resolved_at__isnull=True).update(resolved_at=timezone.now())
            if follow_up_at := serializer.validated_data.get("follow_up_at"):
                FollowUp.objects.create(lead=lead, so=request.user, scheduled_for=follow_up_at)
            LeadAudit.objects.create(lead=lead, actor=request.user, event="status_changed", before={"status": previous}, after={"status": next_status})
        return Response(self.get_serializer(lead).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        lead = self.get_object()
        if lead.status not in {Lead.Status.WON, Lead.Status.LOST, Lead.Status.UNQUALIFIED}:
            return Response({"detail": "Only closed leads can be reopened."}, status=status.HTTP_400_BAD_REQUEST)
        previous = lead.status
        lead.status = Lead.Status.QUALIFIED
        lead.save(update_fields=["status", "updated_at"])
        LeadAudit.objects.create(lead=lead, actor=request.user, event="reopened", before={"status": previous}, after={"status": lead.status})
        return Response(self.get_serializer(lead).data)


class FollowUpViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = FollowUpSerializer

    def get_queryset(self):
        queryset = FollowUp.objects.filter(resolved_at__isnull=True).select_related("lead", "so")
        if not self.request.user.is_admin:
            queryset = queryset.filter(so=self.request.user)
        return queryset.order_by("scheduled_for")

class SystemConfigView(APIView):
    def get(self, request):
        config, _ = SystemConfig.objects.get_or_create(id=1)
        return Response(SystemConfigSerializer(config).data)

    def put(self, request):
        if not request.user.is_admin:
            return Response(status=status.HTTP_403_FORBIDDEN)
        config, _ = SystemConfig.objects.get_or_create(id=1)
        serializer = SystemConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
