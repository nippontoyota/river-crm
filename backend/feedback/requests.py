from django.db import transaction
from django.db.models.functions import Lower, Trim
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from accounts.models import User
from leads.models import Lead
from .models import FeedbackRequest, FeedbackTask
from .questionnaires import CURRENT_VERSION
from .services import allocate, branch_key, lock_feedback


def request_leads(user):
    leads = Lead.objects.filter(deleted_at__isnull=True)
    if user.role in {"ADMIN", "CEO"}:
        return leads
    if user.role == "SALES_MANAGER":
        return leads.annotate(key=Lower(Trim("branch"))).filter(key=branch_key(user.location)) if branch_key(user.location) else leads.none()
    if user.role == "CRE":
        return leads.filter(assigned_so=user)
    if user.role == "SO":
        return leads.filter(assigned_ps=user)
    return leads.none()


class RequestPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active or user.deleted_at:
            return False
        if view.action == "review":
            return user.role in {"ADMIN", "SALES_MANAGER"}
        return user.role in {"ADMIN", "SALES_MANAGER", "CRE", "SO"} or (user.role == "CEO" and request.method in SAFE_METHODS)


class RequestInput(serializers.Serializer):
    lead = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=5000)
    preferred_at = serializers.DateTimeField()

    def validate_preferred_at(self, value):
        if value <= timezone.now():
            raise ValidationError("Choose a future call time.")
        return value


class ReviewInput(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    decision = serializers.ChoiceField(choices=["APPROVED", "REJECTED"])
    review_notes = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    preferred_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if attrs["decision"] == "REJECTED" and not attrs.get("review_notes"):
            raise ValidationError({"review_notes": "Explain why this request was rejected."})
        return attrs


class RequestSerializer(serializers.ModelSerializer):
    customer = serializers.CharField(source="lead.name")
    branch = serializers.CharField(source="lead.branch")
    requester = serializers.CharField(source="requested_by.history_display_name")
    reviewer = serializers.CharField(source="reviewed_by.history_display_name", default=None)

    class Meta:
        model = FeedbackRequest
        fields = ["id", "lead", "customer", "branch", "requester", "reason", "preferred_at", "status", "reviewer", "reviewed_at", "review_notes", "revision", "created_at"]


def approve(row, actor, preferred_at):
    if preferred_at <= timezone.now():
        raise ValidationError({"preferred_at": "Choose a future call time before approving."})
    if FeedbackTask.objects.filter(lead=row.lead, kind="GEN", status="OPEN").exists():
        raise ValidationError("This customer already has an open requested-feedback task.")
    row.status, row.reviewed_by, row.reviewed_at = "APPROVED", actor, timezone.now()
    row.preferred_at = preferred_at
    row.revision += 1
    row.save()
    task = FeedbackTask.objects.create(lead=row.lead, kind="GEN", manual_request=row, origin="MANUAL", occurred_at=row.created_at,
        original_due_at=preferred_at, next_call_at=preferred_at, branch=branch_key(row.lead.branch), questionnaire_version=CURRENT_VERSION)
    allocate(task, "Approved feedback request", actor)


class FeedbackRequestViewSet(mixins.ListModelMixin, GenericViewSet):
    permission_classes = [RequestPermission]
    serializer_class = RequestSerializer

    def get_queryset(self):
        user = self.request.user
        rows = FeedbackRequest.objects.select_related("lead", "requested_by", "reviewed_by")
        if user.role in {"CRE", "SO"}:
            rows = rows.filter(requested_by=user)
        else:
            rows = rows.filter(lead__in=request_leads(user))
        if lead := self.request.query_params.get("lead"):
            if not lead.isdigit():
                raise ValidationError({"lead": "Choose a customer."})
            rows = rows.filter(lead_id=lead)
        if status := self.request.query_params.get("status"):
            rows = rows.filter(status=status)
        return rows.order_by("-created_at", "-id")

    @action(detail=False, methods=["get"])
    def customers(self, request):
        from django.db.models import Q
        q = request.query_params.get("q", "").strip()
        if len(q) < 2:
            return Response([])
        leads = request_leads(request.user).filter(Q(name__icontains=q) | Q(phone__icontains=q)).order_by("name", "id")[:30]
        return Response([{"id": lead.pk, "name": lead.name, "phone": lead.phone, "branch": lead.branch} for lead in leads])

    @transaction.atomic
    def create(self, request):
        data = RequestInput(data=request.data)
        data.is_valid(raise_exception=True)
        actor = User.objects.get(pk=request.user.pk)
        lead = get_object_or_404(request_leads(actor).select_for_update(), pk=data.validated_data["lead"])
        lock_feedback()
        if FeedbackRequest.objects.filter(lead=lead, status="PENDING").exists() or FeedbackTask.objects.filter(lead=lead, kind="GEN", status="OPEN").exists():
            raise ValidationError("This customer already has a pending request or an open requested-feedback call.")
        row = FeedbackRequest.objects.create(lead=lead, requested_by=actor, reason=data.validated_data["reason"], preferred_at=data.validated_data["preferred_at"])
        if actor.role in {"ADMIN", "SALES_MANAGER"}:
            approve(row, actor, row.preferred_at)
        return Response(RequestSerializer(row).data, status=201)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def review(self, request, pk=None):
        data = ReviewInput(data=request.data)
        data.is_valid(raise_exception=True)
        initial = self.get_object()
        get_object_or_404(request_leads(request.user).select_for_update(), pk=initial.lead_id)
        lock_feedback()
        row = self.get_object()
        values = data.validated_data
        if row.status != "PENDING" or row.revision != values["revision"]:
            raise ValidationError("This request changed. Refresh before reviewing it.")
        if row.requested_by_id == request.user.pk:
            raise PermissionDenied("You cannot approve your own sales request.")
        row.review_notes = values.get("review_notes", "")
        if values["decision"] == "APPROVED":
            approve(row, request.user, values.get("preferred_at", row.preferred_at))
        else:
            row.status, row.reviewed_by, row.reviewed_at = "REJECTED", request.user, timezone.now()
            row.revision += 1
            row.save()
        return Response(RequestSerializer(row).data)
