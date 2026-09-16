import re

from rest_framework import serializers

from accounts.models import User
from leads.serializers import configured_values
from .models import ServiceEvent, ServiceRequest, Vehicle
from .permissions import visible_leads, visible_requests


def normalize_chassis(value):
    value = re.sub(r"\s+", "", value).upper()
    if not re.fullmatch(r"[A-Z0-9-]{1,64}", value):
        raise serializers.ValidationError("Enter a chassis number using letters, numbers, or hyphens (up to 64 characters).")
    return value


def configured_branch(value):
    match = next((branch for branch in configured_values("branches") if branch.casefold() == value.strip().casefold()), None)
    if not match:
        raise serializers.ValidationError("Choose a branch from Admin Lists.")
    return match


def validate_vehicle_sale(lead):
    if lead and lead.sales_outcome not in {"BOOKED", "RETAILED"} and lead.status not in {"WALKIN", "WON"}:
        raise serializers.ValidationError({"related_lead": "Vehicle and service records can only be linked to a booked or retailed sale."})


class VehicleSerializer(serializers.ModelSerializer):
    chassis_number = serializers.CharField(max_length=128)
    customer_phone = serializers.RegexField(r"^[0-9]{10}$", required=False)
    customer_name = serializers.CharField(max_length=160, required=False)
    reason = serializers.CharField(max_length=500, write_only=True, required=False)
    sale = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = ["id", "chassis_number", "model", "registration_number", "customer_name", "customer_phone", "customer_email", "related_lead", "sale", "created_at", "reason"]
        read_only_fields = ["created_at"]

    def validate_chassis_number(self, value):
        value = normalize_chassis(value)
        if Vehicle.objects.filter(chassis_number=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("This chassis is already registered. Look it up to use the existing vehicle.")
        return value

    def validate_related_lead(self, lead):
        if lead and not visible_leads(self.context["request"].user).filter(pk=lead.pk).exists():
            raise serializers.ValidationError("Choose a sale you have permission to access.")
        validate_vehicle_sale(lead)
        return lead

    def validate(self, attrs):
        user = self.context["request"].user
        if self.instance:
            if user.role != "ADMIN":
                raise serializers.ValidationError("Only Admin can correct registered vehicle details.")
            if not attrs.get("reason", "").strip():
                raise serializers.ValidationError({"reason": "Explain the correction."})
        lead = attrs.get("related_lead", getattr(self.instance, "related_lead", None))
        if user.role == "SO" and not lead:
            raise serializers.ValidationError({"related_lead": "Choose an accessible CRM sale."})
        if lead:
            attrs.update(customer_name=lead.name, customer_phone=lead.phone, customer_email=lead.email)
        elif not self.instance and (not attrs.get("customer_name") or not attrs.get("customer_phone")):
            raise serializers.ValidationError("Customer name and phone are required for an unlinked vehicle.")
        return attrs

    def get_sale(self, obj):
        lead = obj.related_lead
        return {"id": lead.pk, "branch": lead.branch, "sales_outcome": lead.sales_outcome, "enquiry_date": lead.enquiry_date} if lead else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.update(instance.customer())
        return data


class EventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.history_display_name", read_only=True)

    class Meta:
        model = ServiceEvent
        fields = ["id", "action", "note", "before", "after", "actor_name", "created_at"]


class RequestSerializer(serializers.ModelSerializer):
    ticket_number = serializers.CharField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.history_display_name", read_only=True)
    branch_staff_available = serializers.SerializerMethodField()
    acknowledge_active = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = ServiceRequest
        fields = ["id", "uid", "ticket_number", "vehicle", "customer_snapshot", "vehicle_snapshot", "issue", "branch", "status", "source", "priority", "odometer", "preferred_appointment", "resolution_notes", "resolved_at", "created_by", "created_by_name", "revision", "created_at", "updated_at", "branch_staff_available", "acknowledge_active"]
        read_only_fields = ["uid", "customer_snapshot", "vehicle_snapshot", "status", "resolution_notes", "resolved_at", "created_by", "revision", "created_at", "updated_at"]

    def get_branch_staff_available(self, obj):
        if "service_staff_branches" not in self.context:
            self.context["service_staff_branches"] = {branch.strip().casefold() for branch in User.objects.filter(role="SERVICE", is_active=True, deleted_at__isnull=True).values_list("location", flat=True)}
        return obj.branch.strip().casefold() in self.context["service_staff_branches"]

    def validate_branch(self, value):
        # Existing historical branches can still receive notes and intake edits.
        if self.instance and self.instance.branch == value:
            return value
        return configured_branch(value)

    def validate_issue(self, value):
        if len(value) > 10000:
            raise serializers.ValidationError("Use 10,000 characters or fewer.")
        return value

    def validate_vehicle(self, vehicle):
        if self.instance and vehicle.pk != self.instance.vehicle_id:
            raise serializers.ValidationError("The scooter cannot be changed on an existing request.")
        return vehicle

    def validate(self, attrs):
        if self.context["request"].user.role == "SERVICE":
            branch = self.context["request"].user.location.strip()
            if attrs.get("branch", branch).casefold() != branch.casefold():
                raise serializers.ValidationError({"branch": "Walk-ins must be recorded at your own branch."})
        return attrs


class RequestDetailSerializer(RequestSerializer):
    events = EventSerializer(many=True, read_only=True)
    vehicle_details = VehicleSerializer(source="vehicle", read_only=True)
    history = serializers.SerializerMethodField()

    class Meta(RequestSerializer.Meta):
        fields = RequestSerializer.Meta.fields + ["events", "vehicle_details", "history"]

    def get_history(self, obj):
        return vehicle_history(obj.vehicle, self.context["request"].user, self.context)


def vehicle_history(vehicle, user, context):
    rows = ServiceRequest.objects.all() if user.role == "SERVICE" else visible_requests(user)
    rows = rows.filter(vehicle=vehicle).select_related("created_by").prefetch_related("events__actor").order_by("created_at", "id")
    return [{**RequestSerializer(row, context=context).data, "events": EventSerializer(row.events.all(), many=True).data} for row in rows]


class ActionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=10000, required=False, allow_blank=True, default="")
    branch = serializers.CharField(max_length=120, required=False)
    status = serializers.ChoiceField(choices=["IN_PROGRESS", "WAITING"], required=False)
