from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.models import User
from notifications.models import Notification
from .models import ServiceEvent, ServiceRequest, Vehicle, VehicleEvent
from .permissions import ServicePermission, VehiclePermission, visible_leads, visible_requests
from .serializers import ActionSerializer, RequestDetailSerializer, RequestSerializer, VehicleSerializer, configured_branch, normalize_chassis, vehicle_history


class Conflict(APIException):
    status_code = 409


def active_actor(request):
    actor = User.objects.select_for_update().get(pk=request.user.pk)
    if not actor.is_active or actor.deleted_at:
        raise PermissionDenied("Your account is no longer active.")
    return actor


def event(row, actor, action_name, note="", before=None):
    item = ServiceEvent.objects.create(request=row, actor=actor, action=action_name, note=note, before=before or {},
        after={"status": row.status, "branch": row.branch, "revision": row.revision})
    recipients = set()
    if action_name in {"forward", "transfer", "created"} and row.status != "RECORDED":
        recipients.update(User.objects.filter(role="SERVICE", location__iexact=row.branch, is_active=True, deleted_at__isnull=True).values_list("id", flat=True))
    if row.created_by.role == "CRE" and row.created_by.is_active and not row.created_by.deleted_at and action_name not in {"note", "updated", "created"}:
        recipients.add(row.created_by_id)
    Notification.objects.bulk_create([Notification(user_id=user_id, service_request=row, kind="SERVICE_UPDATE",
        message=f"{row.ticket_number}: {row.get_status_display()} · {row.branch}", dedupe_key=f"service:{item.pk}:{user_id}") for user_id in recipients])


class VehicleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [VehiclePermission]
    serializer_class = VehicleSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        rows = Vehicle.objects.select_related("related_lead")
        chassis = self.request.query_params.get("chassis")
        if chassis:
            rows = rows.filter(chassis_number=normalize_chassis(chassis))
        if user.role == "SO":
            rows = rows.filter(related_lead__in=visible_leads(user))
        elif user.role not in {"ADMIN", "CEO"} and not chassis:
            rows = rows.filter(Q(created_by=user) | Q(related_lead__in=visible_leads(user)) | Q(requests__in=visible_requests(user))).distinct()
        if lead := self.request.query_params.get("lead"):
            if not str(lead).isdigit():
                raise ValidationError({"lead": "Enter a numeric lead ID."})
            rows = rows.filter(related_lead_id=lead)
        return rows.order_by("-id")

    def retrieve(self, request, *args, **kwargs):
        vehicle = self.get_object()
        data = self.get_serializer(vehicle).data
        data["history"] = vehicle_history(vehicle, request.user, self.get_serializer_context())
        data["corrections"] = list(vehicle.events.order_by("created_at").values("reason", "before", "after", "created_at")) if request.user.role == "ADMIN" else []
        return Response(data)

    @transaction.atomic
    def perform_create(self, serializer):
        actor = active_actor(self.request)
        lead = serializer.validated_data.get("related_lead")
        if lead:
            get_object_or_404(visible_leads(actor).select_for_update(), pk=lead.pk)
        serializer.validated_data.pop("reason", None)
        try:
            with transaction.atomic():
                vehicle = serializer.save(created_by=actor)
        except IntegrityError:
            raise Conflict("This chassis has just been registered. Look it up to use the existing vehicle.")
        VehicleEvent.objects.create(vehicle=vehicle, actor=actor, reason="Vehicle registered", after={"chassis_number": vehicle.chassis_number, "related_lead": vehicle.related_lead_id})

    @transaction.atomic
    def perform_update(self, serializer):
        actor = active_actor(self.request)
        if actor.role != "ADMIN":
            raise PermissionDenied("Only Admin can correct vehicle records.")
        row = Vehicle.objects.select_for_update().get(pk=serializer.instance.pk)
        serializer.instance = row
        reason = serializer.validated_data.pop("reason")
        before = dict(Vehicle.objects.filter(pk=row.pk).values("chassis_number", "model", "registration_number", "related_lead_id", "customer_name", "customer_phone", "customer_email").get())
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise Conflict("That chassis is already registered.")
        after = dict(Vehicle.objects.filter(pk=row.pk).values(*before.keys()).get())
        VehicleEvent.objects.create(vehicle=row, actor=actor, reason=reason, before=before, after=after)


class ServiceRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [ServicePermission]
    serializer_class = RequestSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "transition":
            return ActionSerializer
        return RequestDetailSerializer if self.action == "retrieve" else RequestSerializer

    def get_queryset(self):
        rows = visible_requests(self.request.user).select_related("vehicle", "vehicle__related_lead", "created_by").prefetch_related("events__actor")
        params = self.request.query_params
        if self.action != "list":
            return rows
        if state := params.get("status"):
            rows = rows.filter(status=state)
        if branch := params.get("branch"):
            rows = rows.filter(branch__iexact=branch.strip())
        if q := params.get("q", "").strip():
            rows = rows.filter(Q(vehicle__chassis_number__icontains=q) | Q(customer_snapshot__customer_name__icontains=q) | Q(customer_snapshot__customer_phone__icontains=q) | Q(issue__icontains=q) | Q(id=int(q[4:]) if q.upper().startswith("SRV-") and q[4:].isdigit() else -1))
        for key, lookup in (("date_from", "created_at__date__gte"), ("date_to", "created_at__date__lte")):
            if value := params.get(key):
                try:
                    date = parse_date(value)
                except ValueError:
                    date = None
                if not date:
                    raise ValidationError({key: "Use YYYY-MM-DD."})
                rows = rows.filter(**{lookup: date})
        return rows

    @transaction.atomic
    def perform_create(self, serializer):
        actor = active_actor(self.request)
        if actor.role not in {"CRE", "SERVICE"}:
            raise PermissionDenied("CE or branch service staff record new requests.")
        vehicle = Vehicle.objects.select_for_update(of=("self",)).select_related("related_lead").get(pk=serializer.validated_data["vehicle"].pk)
        acknowledged = serializer.validated_data.pop("acknowledge_active", False)
        if vehicle.requests.exclude(status__in=["RESOLVED", "CANCELLED"]).exists() and not acknowledged:
            raise Conflict({"detail": "This scooter already has an active service request. Confirm this is a separate issue before saving.", "active_request": True})
        if actor.role == "SERVICE" and serializer.validated_data["branch"].casefold() != actor.location.strip().casefold():
            raise PermissionDenied("Record walk-ins at your current branch.")
        row = serializer.save(created_by=actor, status="FORWARDED" if actor.role == "SERVICE" else "RECORDED",
            customer_snapshot=vehicle.customer(), vehicle_snapshot={"chassis_number": vehicle.chassis_number, "model": vehicle.model, "registration_number": vehicle.registration_number, "related_lead": vehicle.related_lead_id})
        event(row, actor, "created")

    def locked_request(self):
        actor = active_actor(self.request)
        row = get_object_or_404(visible_requests(actor).select_for_update(), pk=self.kwargs["pk"])
        revision = self.request.data.get("revision")
        if str(revision) != str(row.revision):
            raise Conflict("This request changed. Refresh it before saving again.")
        return actor, row

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        actor, row = self.locked_request()
        if actor.role != "CRE" or row.created_by_id != actor.pk or row.status != "RECORDED":
            raise PermissionDenied("Only the originating CE can edit intake details before forwarding.")
        serializer = self.get_serializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("acknowledge_active", None)
        before = {key: str(getattr(row, key)) for key in serializer.validated_data}
        row = serializer.save(revision=row.revision + 1)
        event(row, actor, "updated", before=before)
        return Response(RequestDetailSerializer(row, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="(?P<operation>forward|progress|note|resolve|reopen|cancel|transfer)")
    @transaction.atomic
    def transition(self, request, pk=None, operation=None):
        data = ActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        actor, row = self.locked_request()
        values = data.validated_data
        note = values["note"].strip()
        before = {"status": row.status, "branch": row.branch, "resolution_notes": row.resolution_notes, "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None}
        operator = actor.role in {"ADMIN", "SERVICE"}
        active = row.status in {"FORWARDED", "IN_PROGRESS", "WAITING"}
        if operation == "forward":
            if actor.role != "CRE" or row.status != "RECORDED":
                raise PermissionDenied("Only CE can forward a recorded request.")
            row.branch = configured_branch(values.get("branch", row.branch))
            row.status = "FORWARDED"
        elif operation == "note":
            if actor.role not in {"ADMIN", "SERVICE", "CRE"}:
                raise PermissionDenied()
        elif operation == "transfer":
            if actor.role != "ADMIN" or not active:
                raise PermissionDenied("Admin can transfer active requests.")
            row.branch = configured_branch(values.get("branch", ""))
            if row.branch == before["branch"]:
                raise ValidationError({"branch": "Choose a different branch."})
            row.status = "FORWARDED"
        elif operation == "cancel":
            if not ((operator and active) or (actor.role == "CRE" and row.status == "RECORDED")):
                raise PermissionDenied("This request cannot be cancelled here.")
            row.status = "CANCELLED"
        elif operation == "reopen":
            if not operator or row.status != "RESOLVED":
                raise PermissionDenied("Only resolved requests can be reopened by service staff or Admin.")
            row.status, row.resolved_at, row.resolution_notes = "IN_PROGRESS", None, ""
        elif operation == "resolve":
            if not operator or row.status not in {"IN_PROGRESS", "WAITING"}:
                raise PermissionDenied("Start work before resolving the request.")
            row.status, row.resolved_at, row.resolution_notes = "RESOLVED", timezone.now(), note
        elif operation == "progress":
            target = values.get("status")
            if not operator or not active:
                raise PermissionDenied("Only service staff or Admin can update active requests.")
            if target not in {"IN_PROGRESS", "WAITING"} or target == row.status or (row.status == "FORWARDED" and target != "IN_PROGRESS"):
                raise ValidationError({"status": "Start work, or move between In progress and Waiting."})
            row.status = target
        if (operation in {"note", "resolve", "reopen", "cancel", "transfer"} or row.status == "WAITING") and not note:
            raise ValidationError({"note": "A reason or note is required."})
        row.revision += 1
        row.save()
        event(row, actor, operation, note, before)
        return Response(RequestDetailSerializer(row, context=self.get_serializer_context()).data)
