"""Shared CE assistance. Assignment ownership and outbound work stay separate."""
import hashlib
import json

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsActiveAdminOrCRE
from complaints.models import Complaint, ComplaintNote
from complaints.serializers import ComplaintCreateSerializer, ComplaintDetailSerializer
from ceo.tracking import complaint_event
from intake.mapping import normalize_phone
from servicing.models import ServiceRequest, Vehicle
from servicing.serializers import EventSerializer, RequestSerializer, VehicleSerializer, validate_vehicle_sale
from servicing.views import Conflict, event as service_event
from .models import FollowUp, InboundInteraction, Lead, LeadAudit
from .outcomes import is_closed
from .phone_lock import lock_phones
from .serializers import LeadDetailSerializer, OwnerContactSerializer, SOLeadUpdateSerializer
from .views import LeadViewSet

CALL_KINDS = {"NOTE", "CALLBACK", "COMPLAINT", "SERVICE", "COMPLAINT_NOTE", "SERVICE_NOTE"}


def callback_destination(lead):
    sales = bool(lead.assigned_ps_id or lead.needs_so_reassignment or lead.status in {"QUALIFIED", "WALKIN", "WON"})
    owner = lead.assigned_ps if sales else lead.assigned_so
    held = lead.needs_so_reassignment if sales else lead.needs_cre_reassignment
    role = "SO" if sales else "CRE"
    available = bool(owner and owner.role == role and owner.is_active and not owner.deleted_at and not held)
    return {"role": role, "owner": OwnerContactSerializer(owner).data if owner else None, "available": available}


def followup_version(row):
    value = f"{row.pk}:{row.so_id}:{row.scheduled_for.isoformat()}:{row.resolved_at}:{row.reminder_held}"
    return hashlib.sha256(value.encode()).hexdigest()


def followup_data(row):
    return {"id": row.pk, "lead_id": row.lead_id, "customer": row.lead.name, "phone": row.lead.phone,
            "owner_id": row.so_id, "owner_name": row.so.history_display_name, "scheduled_for": row.scheduled_for,
            "resolved_at": row.resolved_at, "reminder_held": row.reminder_held, "origin": row.origin,
            "version": followup_version(row)}


def interaction_data(row):
    return {"id": row.pk, "kind": row.kind, "state": row.state, "lead_id": row.lead_id,
            "customer": row.lead.name if row.lead else row.caller_name, "caller_name": row.caller_name,
            "caller_phone": row.caller_phone, "reason": row.reason, "notes": row.notes,
            "handled_by": row.handled_by_id, "handled_by_name": row.handled_by.history_display_name,
            "callback_at": row.callback_at, "follow_up_id": row.follow_up_id,
            "complaint_id": row.complaint_id, "service_request_id": row.service_request_id,
            "owner_snapshot": row.owner_snapshot, "review_of": row.review_of_id,
            "created_at": row.created_at, "updated_at": row.updated_at}


def interaction_rows():
    return InboundInteraction.objects.select_related("lead", "handled_by")


def check_version(actual, supplied):
    if not supplied or (actual != supplied and str(actual) != str(supplied)):
        raise Conflict("This record changed. Refresh it before saving again; keep your draft.")


def check_lead_version(lead, supplied):
    field = serializers.DateTimeField()
    if not supplied:
        raise ValidationError({"lead_version": "Refresh the customer record before saving."})
    check_version(lead.updated_at, field.run_validation(supplied))


def submission(request, lead_id=None):
    """Serialize retries before any writes. The UUID is unique across actors and operations."""
    if not isinstance(request.data, dict):
        raise ValidationError("Send a JSON object.")
    key = serializers.UUIDField().run_validation(request.data.get("submission_id"))
    lock_phones(f"call-center:{key}")
    user_ids = {request.user.pk}
    target = lead_id or request.data.get("lead_id")
    if target:
        target = serializers.IntegerField(min_value=1).run_validation(target)
        owners = Lead.objects.filter(pk=target).values_list("assigned_so_id", "assigned_ps_id").first()
        if owners:
            user_ids.update(value for value in owners if value)
    if request.data.get("ps_officer_id"):
        user_ids.add(serializers.IntegerField(min_value=1).run_validation(request.data["ps_officer_id"]))
    # Stable lock order also matches account offboarding; callers can assist each other.
    locked_users = {user.pk: user for user in User.objects.select_for_update(no_key=True).filter(pk__in=user_ids).order_by("pk")}
    actor = locked_users[request.user.pk]
    if not actor.is_active or actor.deleted_at:
        raise PermissionDenied("Your account is no longer active.")
    fingerprint = hashlib.sha256(json.dumps({"path": request.path, "data": request.data}, sort_keys=True, default=str).encode()).hexdigest()
    previous = interaction_rows().filter(submission_id=key).first()
    if previous and (previous.handled_by_id != actor.pk or previous.fingerprint != fingerprint):
        raise Conflict("This submission ID has already been used for a different action.")
    return actor, {"submission_id": key, "fingerprint": fingerprint}, previous


def audit_interaction(row):
    if row.lead:
        LeadAudit.objects.create(lead=row.lead, actor=row.handled_by, event="inbound_interaction",
                                after={"interaction_id": row.pk, "kind": row.kind, "state": row.state})


def ticket_rows(lead):
    complaints = Complaint.objects.filter(Q(related_lead=lead) | Q(related_lead__isnull=True, customer_phone=lead.phone)).select_related("logged_by", "assigned_to").prefetch_related("notes__author")
    services = ServiceRequest.objects.filter(
        Q(vehicle__related_lead=lead) | Q(vehicle__related_lead__isnull=True, vehicle__customer_phone=lead.phone)
        | Q(inboundinteraction__lead=lead)).distinct().select_related("created_by", "vehicle").prefetch_related("events__actor")
    return complaints, services


def shared_detail(lead, request):
    data = LeadDetailSerializer(lead, context={"request": request, "call_center": True}).data
    data["callback_destination"] = callback_destination(lead)
    data["callbacks"] = [followup_data(row) for row in lead.follow_ups.select_related("lead", "so").filter(resolved_at__isnull=True).order_by("scheduled_for", "id")]
    data["interactions"] = [interaction_data(row) for row in interaction_rows().filter(lead=lead)[:50]]
    data["vehicles"] = VehicleSerializer(lead.vehicles.all(), many=True, context={"request": request}).data
    # Tickets/history are separately paginated so no duplicate can be hidden by a detail limit.
    return data


class CallCenterLeadViewSet(LeadViewSet):
    shared_call_center = True
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        return [IsActiveAdminOrCRE()]

    def get_queryset(self):
        return Lead.objects.filter(deleted_at__isnull=True).select_related("assigned_so", "assigned_ps", "qualification")

    def retrieve(self, request, *args, **kwargs):
        return Response(shared_detail(self.get_object(), request))

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        if isinstance(request.data, dict) and "phone" in request.data:
            # Match the lock order used by personal edits and intake before locking the lead.
            phone = SOLeadUpdateSerializer().fields["phone"].run_validation(request.data["phone"])
            old_phone = Lead.objects.filter(pk=kwargs["pk"]).values_list("phone", flat=True).first()
            lock_phones(old_phone, phone)
        actor, receipt, previous = submission(request, kwargs["pk"])
        if previous:
            return Response(shared_detail(self.get_object(), request))
        lead = get_object_or_404(Lead.objects.select_for_update(), pk=kwargs["pk"], deleted_at__isnull=True)
        check_lead_version(lead, request.data.get("lead_version"))
        if is_closed(lead):
            raise ValidationError("Closed leads can receive inbound assistance, but only Admin can reopen them.")
        allowed = set(SOLeadUpdateSerializer().fields) - {"follow_up_at", "call_status", "whatsapp_agreed"}
        unknown = set(request.data) - allowed - {"submission_id", "lead_version"}
        if unknown:
            raise ValidationError({field: "This field cannot be changed through call-center lead updates." for field in unknown})
        if request.data.get("ps_officer_id") and not lead.assigned_ps_id:
            if lead.needs_so_reassignment or lead.status not in {"FRESH", "PENDING", "RNR", "SWITCHED_OFF", "CALLBACK"} or request.data.get("call_outcome") != "QUALIFIED":
                raise ValidationError({"ps_officer_id": "Assign a PS only during first qualification. Ask Admin for reassignment."})
        response = self.so_update(request, kwargs["pk"])
        if response.status_code >= 400:
            transaction.set_rollback(True)
            return response
        lead.refresh_from_db()
        row = InboundInteraction.objects.create(**receipt, kind="LEAD_UPDATE", lead=lead, handled_by=actor,
            notes=str(request.data.get("remarks") or "Customer record updated"), owner_snapshot={"assigned_ce": lead.assigned_so_id, "assigned_ps": lead.assigned_ps_id})
        audit_interaction(row)
        return Response(shared_detail(self.get_object(), request))


class InputSerializer(serializers.Serializer):
    submission_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=sorted(CALL_KINDS | {"CALLBACK_COMPLETE", "CALLBACK_RESCHEDULE", "REVIEW"}))
    lead_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    lead_version = serializers.DateTimeField(required=False)
    confirm_customer = serializers.BooleanField(default=False)
    caller_name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    caller_phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=10000)
    callback_at = serializers.DateTimeField(required=False)
    follow_up_id = serializers.IntegerField(min_value=1, required=False)
    follow_up_version = serializers.CharField(required=False)
    ticket_id = serializers.IntegerField(min_value=1, required=False)
    ticket_version = serializers.CharField(required=False)
    confirm_ticket = serializers.BooleanField(default=False)
    acknowledge_active = serializers.BooleanField(default=False)
    complaint = serializers.DictField(required=False)
    service = serializers.DictField(required=False)
    interaction_id = serializers.IntegerField(min_value=1, required=False)
    interaction_version = serializers.DateTimeField(required=False)
    review_state = serializers.ChoiceField(choices=["RECORDED", "RESOLVED"], required=False, default="RESOLVED")

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise ValidationError({field: "Unknown field." for field in unknown})
        if attrs["caller_phone"]:
            attrs["caller_phone"] = normalize_phone(attrs["caller_phone"])
            if not attrs["caller_phone"]:
                raise ValidationError({"caller_phone": "Enter a complete customer phone number."})
        if attrs["kind"] in CALL_KINDS:
            if not attrs["caller_phone"] or not attrs["reason"]:
                raise ValidationError("Caller phone and reason are required for an inbound call.")
        if attrs.get("callback_at") and attrs["callback_at"] <= timezone.now():
            raise ValidationError({"callback_at": "Choose a future callback time."})
        if attrs["kind"] in {"CALLBACK", "CALLBACK_RESCHEDULE"} and not attrs.get("callback_at"):
            raise ValidationError({"callback_at": "Choose a callback time."})
        if attrs.get("lead_id") and (not attrs.get("lead_version") or not attrs["confirm_customer"]):
            raise ValidationError("Confirm the selected customer and refresh their record before saving.")
        if not attrs.get("lead_id") and attrs["kind"] not in {"NOTE", "CALLBACK", "COMPLAINT", "SERVICE", "REVIEW"}:
            raise ValidationError({"lead_id": "Select the matching enquiry first."})
        return attrs


def schedule_callback(lead, at):
    destination = callback_destination(lead)
    if not destination["available"]:
        return None
    owner = User.objects.select_for_update().get(pk=destination["owner"]["id"])
    if not owner.is_active or owner.deleted_at:
        return None
    return FollowUp.objects.create(lead=lead, so=owner, scheduled_for=at, origin="INBOUND")


def save_interaction(request, callback_only=False):
    actor, receipt, previous = submission(request)
    if previous:
        return previous
    serializer = InputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    kind = data["kind"]
    if callback_only and kind not in {"CALLBACK_COMPLETE", "CALLBACK_RESCHEDULE"}:
        raise PermissionDenied("Use this action only to complete or reschedule your callback.")
    if kind == "REVIEW" and not actor.is_admin:
        raise PermissionDenied("Only Admin can review unmatched enquiries and routing exceptions.")
    lead = None
    if data.get("lead_id"):
        lead = get_object_or_404(Lead.objects.select_for_update(), pk=data["lead_id"], deleted_at__isnull=True)
        check_version(lead.updated_at, data["lead_version"])
    row = InboundInteraction(**receipt, handled_by=actor, kind=kind, lead=lead,
        caller_name=data["caller_name"], caller_phone=data["caller_phone"], reason=data["reason"], notes=data["notes"],
        callback_at=data.get("callback_at"), owner_snapshot={"assigned_ce": lead.assigned_so_id, "assigned_ps": lead.assigned_ps_id} if lead else {})
    if kind == "REVIEW":
        original = get_object_or_404(InboundInteraction.objects.select_for_update(), pk=data.get("interaction_id"))
        check_version(original.updated_at, data.get("interaction_version"))
        if original.state not in {"UNMATCHED", "AWAITING_ROUTING"}:
            raise Conflict("This enquiry has already been reviewed.")
        if original.lead_id and (not lead or original.lead_id != lead.pk):
            raise ValidationError("A matched enquiry cannot be moved to a different lead.")
        original.lead = lead
        original.state = data["review_state"]
        if original.kind == "CALLBACK" and original.state == "RECORDED":
            if not lead or not data.get("callback_at"):
                raise ValidationError("Select a lead and a future callback time to route this callback.")
            original.callback_at = data["callback_at"]
            original.follow_up = schedule_callback(lead, original.callback_at)
            if not original.follow_up:
                raise ValidationError("Assign an active owner before routing this callback.")
        original.save(update_fields=["lead", "state", "callback_at", "follow_up", "updated_at"])
        row.review_of = original
        row.state = "RESOLVED"
    elif not lead:
        row.state = "UNMATCHED"
    elif kind == "CALLBACK":
        row.follow_up = schedule_callback(lead, data["callback_at"])
        if not row.follow_up:
            row.state = "AWAITING_ROUTING"
    elif kind in {"CALLBACK_COMPLETE", "CALLBACK_RESCHEDULE"}:
        followup = get_object_or_404(FollowUp.objects.select_for_update(), pk=data.get("follow_up_id"), lead=lead)
        if callback_only and not actor.is_admin and followup.so_id != actor.pk:
            raise PermissionDenied("This callback is not assigned to you.")
        check_version(followup_version(followup), data.get("follow_up_version"))
        if followup.resolved_at:
            raise Conflict("This callback has already been completed.")
        before = {"scheduled_for": followup.scheduled_for.isoformat(), "resolved_at": None}
        if kind == "CALLBACK_COMPLETE":
            followup.resolved_at = timezone.now()
        else:
            followup.scheduled_for = data["callback_at"]
            followup.notified_at = None
        followup.save(update_fields=["resolved_at", "scheduled_for", "notified_at"])
        row.follow_up = followup
        LeadAudit.objects.create(lead=lead, actor=actor, event="callback_updated", before=before,
            after={"follow_up_id": followup.pk, "scheduled_for": followup.scheduled_for.isoformat(), "resolved_at": str(followup.resolved_at) if followup.resolved_at else None})
    elif kind == "COMPLAINT":
        if not data.get("complaint"):
            row.state = "AWAITING_ROUTING"
        else:
            existing = ticket_rows(lead)[0].exclude(status__in=["RESOLVED", "CLOSED"])
            if existing.exists() and not data["acknowledge_active"]:
                raise Conflict("This customer has an open complaint. Select that ticket or confirm this is a separate issue.")
            values = {**data["complaint"], "customer_name": lead.name, "customer_phone": lead.phone, "customer_email": lead.email, "source": "PHONE"}
            form = ComplaintCreateSerializer(data=values, context={"request": request})
            form.is_valid(raise_exception=True)
            row.complaint = form.save(logged_by=actor, related_lead=lead)
            complaint_event(row.complaint, actor, "complaint_created")
    elif kind == "SERVICE":
        if not data.get("service") or not data["service"].get("vehicle"):
            row.state = "AWAITING_ROUTING"
        else:
            vehicle_id = serializers.IntegerField(min_value=1).run_validation(data["service"]["vehicle"])
            vehicle = get_object_or_404(Vehicle.objects.select_for_update(), pk=vehicle_id, related_lead=lead)
            validate_vehicle_sale(lead)
            if vehicle.requests.exclude(status__in=["RESOLVED", "CANCELLED"]).exists() and not data["acknowledge_active"]:
                raise Conflict("This vehicle has an active service request. Select it or confirm this is a separate issue.")
            form = RequestSerializer(data={**data["service"], "source": "PHONE"}, context={"request": request})
            form.is_valid(raise_exception=True)
            form.validated_data.pop("acknowledge_active", None)
            row.service_request = form.save(created_by=actor, status="RECORDED", customer_snapshot=vehicle.customer(),
                vehicle_snapshot={"chassis_number": vehicle.chassis_number, "model": vehicle.model, "registration_number": vehicle.registration_number, "related_lead": lead.pk})
            service_event(row.service_request, actor, "created")
            row.service_request.status = "FORWARDED"
            row.service_request.revision += 1
            row.service_request.save(update_fields=["status", "revision", "updated_at"])
            service_event(row.service_request, actor, "forward", note=data["notes"])
    elif kind in {"COMPLAINT_NOTE", "SERVICE_NOTE"}:
        if not data["confirm_ticket"]:
            raise ValidationError("Confirm that the selected ticket is the customer's request.")
        complaints, services = ticket_rows(lead)
        if kind == "COMPLAINT_NOTE":
            ticket = get_object_or_404(Complaint.objects.select_for_update(), pk=data.get("ticket_id"))
            if not complaints.filter(pk=ticket.pk).exists():
                raise PermissionDenied("This complaint does not match the selected customer.")
            check_lead_version(ticket, data.get("ticket_version"))
            ComplaintNote.objects.create(complaint=ticket, author=actor, content=data["notes"])
            ticket.related_lead = lead
            ticket.save(update_fields=["related_lead", "updated_at"])
            complaint_event(ticket, actor, "inbound_message")
            row.complaint = ticket
        else:
            ticket = get_object_or_404(ServiceRequest.objects.select_for_update(), pk=data.get("ticket_id"))
            if not services.filter(pk=ticket.pk).exists():
                raise PermissionDenied("This service request does not match the selected customer.")
            check_version(ticket.revision, data.get("ticket_version"))
            ticket.revision += 1
            ticket.save(update_fields=["revision", "updated_at"])
            service_event(ticket, actor, "note", note=data["notes"])
            row.service_request = ticket
    row.save()
    audit_interaction(row)
    return row


class InteractionView(APIView):
    permission_classes = [IsActiveAdminOrCRE]

    def get(self, request):
        rows = interaction_rows().filter(Q(lead__deleted_at__isnull=True))
        if request.query_params.get("pending") == "true":
            if not request.user.is_admin:
                raise PermissionDenied("Admin reviews routing exceptions.")
            rows = rows.filter(state__in=["UNMATCHED", "AWAITING_ROUTING"])
        if lead := request.query_params.get("lead"):
            lead_id = serializers.IntegerField(min_value=1).run_validation(lead)
            rows = rows.filter(lead_id=lead_id)
        elif not request.user.is_admin:
            rows = rows.filter(handled_by=request.user)
        if request.query_params.get("calls_only") == "true":
            rows = rows.filter(kind__in=CALL_KINDS)
        pagination = PageNumberPagination()
        page = pagination.paginate_queryset(rows, request)
        return pagination.get_paginated_response([interaction_data(row) for row in page])

    @transaction.atomic
    def post(self, request):
        row = save_interaction(request)
        return Response(interaction_data(row), status=status.HTTP_201_CREATED)


class TicketView(APIView):
    permission_classes = [IsActiveAdminOrCRE]

    def get(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk, deleted_at__isnull=True)
        kind = request.query_params.get("kind", "complaint")
        complaints, services = ticket_rows(lead)
        if kind not in {"complaint", "service"}:
            raise ValidationError({"kind": "Choose complaint or service."})
        rows = complaints if kind == "complaint" else services
        if ticket_id := request.query_params.get("ticket_id"):
            rows = rows.filter(pk=serializers.IntegerField(min_value=1).run_validation(ticket_id))
        pagination = PageNumberPagination()
        page = pagination.paginate_queryset(rows.order_by("-created_at", "-id"), request)
        if kind == "complaint":
            data = [{**ComplaintDetailSerializer(row).data, "confirmed_link": row.related_lead_id == lead.pk} for row in page]
        else:
            context = {"request": request}
            data = [{**RequestSerializer(row, context=context).data, "events": EventSerializer(row.events.all(), many=True).data,
                     "confirmed_link": row.vehicle.related_lead_id == lead.pk} for row in page]
        return pagination.get_paginated_response(data)


class CallbackPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and not user.deleted_at and user.role in {"CRE", "SO", "ADMIN"})


class CallbackView(APIView):
    permission_classes = [CallbackPermission]

    def get(self, request):
        rows = FollowUp.objects.filter(origin="INBOUND", resolved_at__isnull=True, lead__deleted_at__isnull=True).select_related("lead", "so").prefetch_related("inbound_interactions")
        if not request.user.is_admin:
            rows = rows.filter(so=request.user)
        pagination = PageNumberPagination()
        page = pagination.paginate_queryset(rows.order_by("scheduled_for", "id"), request)
        return pagination.get_paginated_response([{**followup_data(row), "lead_version": row.lead.updated_at,
            "notes": [item.notes for item in row.inbound_interactions.all() if item.kind == "CALLBACK"]} for row in page])

    @transaction.atomic
    def post(self, request):
        return Response(interaction_data(save_interaction(request, callback_only=True)))


class CallCenterSummaryView(APIView):
    permission_classes = [IsActiveAdminOrCRE]

    def get(self, request):
        rows = InboundInteraction.objects.filter(kind__in=CALL_KINDS, created_at__date=timezone.localdate(), lead__deleted_at__isnull=True)
        if not request.user.is_admin:
            rows = rows.filter(handled_by=request.user)
        return Response({"inbound_calls_today": rows.count(), "by_handler": list(rows.values("handled_by", "handled_by__first_name", "handled_by__last_name", "handled_by__email").annotate(count=Count("id")).order_by("handled_by"))})
