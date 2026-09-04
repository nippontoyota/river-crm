from rest_framework import serializers
from django.utils import timezone

from accounts.models import User
from .models import CallLog, FollowUp, Lead, LeadAudit, LeadQualification, SystemConfig


def normalize_sources(values):
    sources = [Lead.Source.WALKIN]
    seen = {"walkin"}
    for value in values if isinstance(values, list) else []:
        source = str(value).strip()
        key = "".join(character for character in source.casefold() if character.isalnum())
        if not source or key in seen:
            continue
        seen.add(key)
        sources.append(source)
    return sources


def configured_values(name):
    lists = SystemConfig.objects.filter(id=1).values_list("lists", flat=True).first() or {}
    values = [str(value).strip() for value in lists.get(name, []) if str(value).strip()] if isinstance(lists.get(name, []), list) else []
    return normalize_sources(values) if name == "sources" else values


def configured_source(value):
    source = (value or "").strip()
    key = "".join(character for character in source.casefold() if character.isalnum())
    if key == "walkin":
        return Lead.Source.WALKIN
    return next((allowed for allowed in configured_values("sources") if allowed.casefold() == source.casefold()), "")


def validate_configured_source(value, current=""):
    source = configured_source(value)
    if source:
        return source
    if current and value == current:
        return value
    raise serializers.ValidationError("Choose a lead source from Admin Lists.")


def validate_configured_choice(value, list_name, label):
    value = (value or "").strip()
    allowed = configured_values(list_name)
    if value and allowed and value not in allowed:
        raise serializers.ValidationError(f"Choose a {label} from Admin Lists.")
    return value


PS_CALL_OUTCOME_STATUS_OPTIONS = {
    "Need Test Drive": {Lead.Status.PENDING},
    "Showroom Visit": {Lead.Status.PENDING},
    "Exchange Issue": {Lead.Status.PENDING},
    "Booking Done": {Lead.Status.WALKIN},
    "Retail Done": {Lead.Status.WON},
    "Need time": {Lead.Status.PENDING},
    "Need SO Call": {Lead.Status.PENDING},
    "Need More Details": {Lead.Status.PENDING},
    "Discount Issue": {Lead.Status.PENDING},
    "Not Interested": {Lead.Status.LOST},
    "Already Booked": {Lead.Status.LOST},
    "Lost to Competition": {Lead.Status.LOST},
    "Finance Rejected": {Lead.Status.LOST},
    "Dropped": {Lead.Status.LOST},
    "Lost to co-dealer": {Lead.Status.LOST},
    "No Response": {Lead.Status.LOST},
    "RNR": {Lead.Status.RNR, Lead.Status.PENDING},
    "Switch Off": {Lead.Status.SWITCHED_OFF, Lead.Status.PENDING},
    "Call Me Back": {Lead.Status.CALLBACK, Lead.Status.PENDING},
    "Call Forwarding": {Lead.Status.PENDING},
    "Line Busy": {Lead.Status.PENDING},
    "Invalid Number": {Lead.Status.PENDING},
}

CALL_OUTCOME_STATUS_OPTIONS = {
    "PENDING": {Lead.Status.PENDING},
    "QUALIFIED": {Lead.Status.QUALIFIED},
    "LOST": {Lead.Status.LOST},
    "RNR": {Lead.Status.RNR},
    "SWITCHED_OFF": {Lead.Status.SWITCHED_OFF},
    "CALLBACK": {Lead.Status.CALLBACK},
    **PS_CALL_OUTCOME_STATUS_OPTIONS,
}


class QualificationSerializer(serializers.ModelSerializer):
    def validate_variant(self, value):
        return validate_configured_choice(value, "colorVariants", "color variant")

    class Meta:
        model = LeadQualification
        fields = ["variant", "buying_timeline", "finance_type", "trade_in", "test_drive", "notes", "updated_at"]
        read_only_fields = ["updated_at"]


class LeadSerializer(serializers.ModelSerializer):
    assigned_so_name = serializers.CharField(source="assigned_so.history_display_name", read_only=True)
    assigned_ps_name = serializers.CharField(source="assigned_ps.history_display_name", read_only=True)
    next_follow_up = serializers.SerializerMethodField()
    call_count = serializers.SerializerMethodField()
    qualification = serializers.SerializerMethodField()
    qualification_input = QualificationSerializer(required=False, write_only=True)

    def get_next_follow_up(self, obj):
        if hasattr(obj, "_next_follow_up"):
            return obj._next_follow_up
        follow_ups = getattr(obj, "_open_followups", None)
        if follow_ups is None:
            follow_ups = obj.follow_ups.filter(resolved_at__isnull=True).order_by("scheduled_for")[:1]
        return follow_ups[0].scheduled_for if follow_ups else None

    def get_call_count(self, obj):
        return getattr(obj, "_call_count", None) if hasattr(obj, "_call_count") else obj.call_logs.count()

    def get_qualification(self, obj):
        qualification = getattr(obj, "qualification", None)
        return QualificationSerializer(qualification).data if qualification else None

    def validate_enquiry_date(self, value):
        if value and value > timezone.localdate():
            raise serializers.ValidationError("Enquiry date cannot be in the future.")
        return value

    def validate_model_interest(self, value):
        return validate_configured_choice(value, "models", "vehicle model")

    def validate_source(self, value):
        return validate_configured_source(value, self.instance.source if self.instance else "")

    ps_officer_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role=User.Role.SALES_OFFICER, is_active=True, deleted_at__isnull=True), source="assigned_ps", required=False, write_only=True)

    class Meta:
        model = Lead
        fields = ["id", "uid", "name", "phone", "email", "source", "source_label", "campaign", "model_interest", "city", "branch", "enquiry_date", "status", "category", "sales_outcome", "assigned_so", "assigned_so_name", "assigned_ps", "assigned_ps_name", "ps_officer_id", "next_follow_up", "call_count", "qualification", "qualification_input", "flagged_to_manager", "needs_cre_reassignment", "needs_so_reassignment", "profession", "created_at", "updated_at"]
        read_only_fields = ["uid", "assigned_so", "assigned_ps", "needs_cre_reassignment", "needs_so_reassignment", "created_at", "updated_at"]
        extra_kwargs = {"source": {"required": True}}

    def create(self, validated_data):
        qualification_data = validated_data.pop("qualification_input", None)
        lead = super().create(validated_data)
        if qualification_data:
            LeadQualification.objects.create(lead=lead, **qualification_data)
        return lead


class SOLeadListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = ["id", "status", "name", "phone", "source", "flagged_to_manager"]


class LeadDetailSerializer(LeadSerializer):
    call_history = serializers.SerializerMethodField()
    follow_up_history = serializers.SerializerMethodField()
    audit_history = serializers.SerializerMethodField()

    def get_call_history(self, obj):
        return CallLogSerializer(obj.call_logs.select_related("so").order_by("-created_at"), many=True).data

    def get_follow_up_history(self, obj):
        return FollowUpSerializer(obj.follow_ups.select_related("so").order_by("-scheduled_for"), many=True).data

    def get_audit_history(self, obj):
        return [{"event": event.event, "before": event.before, "after": event.after, "actor": event.actor.history_display_name if event.actor else "System", "created_at": event.created_at} for event in obj.audit_events.select_related("actor").order_by("-created_at")[:30]]

    class Meta(LeadSerializer.Meta):
        fields = LeadSerializer.Meta.fields + ["call_history", "follow_up_history", "audit_history"]


class CallLogSerializer(serializers.ModelSerializer):
    so_name = serializers.CharField(source="so.history_display_name", read_only=True)

    class Meta:
        model = CallLog
        fields = ["id", "status", "call_status", "outcome", "remarks", "so_name", "created_at"]
        read_only_fields = ["id", "created_at"]


class LeadUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Lead.Status.choices)
    remarks = serializers.CharField(max_length=500, required=False, allow_blank=True)
    call_status = serializers.CharField(max_length=20, required=False, allow_blank=True)
    call_outcome = serializers.CharField(max_length=50, required=False, allow_blank=True)
    follow_up_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        follow_up_at = attrs.get("follow_up_at")
        if attrs["status"] in [Lead.Status.CALLBACK, Lead.Status.WALKIN] and not follow_up_at:
            raise serializers.ValidationError({"follow_up_at": "This status requires a follow-up time."})
        if attrs["status"] not in [Lead.Status.CALLBACK, Lead.Status.WALKIN] and follow_up_at:
            raise serializers.ValidationError({"follow_up_at": "Only callbacks and walk-ins can have an appointment."})
        if follow_up_at and follow_up_at <= timezone.now():
            raise serializers.ValidationError({"follow_up_at": "Choose a future appointment time."})
        return attrs


class SOLeadUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False)
    phone = serializers.RegexField(regex=r"^\d{10}$", required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    source = serializers.CharField(max_length=100, required=False)
    source_label = serializers.CharField(max_length=100, required=False, allow_blank=True)
    campaign = serializers.CharField(max_length=160, required=False, allow_blank=True)
    model_interest = serializers.CharField(max_length=100, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=Lead.Status.choices, required=False, allow_blank=True)
    category = serializers.ChoiceField(choices=Lead.Category.choices, required=False)
    sales_outcome = serializers.ChoiceField(choices=Lead.SalesOutcome.choices, required=False)
    branch = serializers.CharField(max_length=120, required=False, allow_blank=True)
    enquiry_date = serializers.DateField(required=False, allow_null=True)
    remarks = serializers.CharField(max_length=500, required=False, allow_blank=True)
    call_status = serializers.CharField(max_length=20, required=False, allow_blank=True)
    call_outcome = serializers.CharField(max_length=50, required=False, allow_blank=True)
    follow_up_at = serializers.DateTimeField(required=False, allow_null=True)
    qualification = QualificationSerializer(required=False)
    ps_officer_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role=User.Role.SALES_OFFICER, is_active=True, deleted_at__isnull=True), source="ps_officer", required=False)
    flagged_to_manager = serializers.BooleanField(required=False)

    def validate_model_interest(self, value):
        return validate_configured_choice(value, "models", "vehicle model")

    def validate_source(self, value):
        return validate_configured_source(value, self.context.get("current_source", ""))

    def validate(self, attrs):
        enquiry_date = attrs.get("enquiry_date")
        if enquiry_date and enquiry_date > timezone.localdate():
            raise serializers.ValidationError({"enquiry_date": "Enquiry date cannot be in the future."})
        next_status = attrs.get("status") or {"PENDING": Lead.Status.PENDING, "QUALIFIED": Lead.Status.QUALIFIED, "LOST": Lead.Status.LOST, "RNR": Lead.Status.RNR, "SWITCHED_OFF": Lead.Status.SWITCHED_OFF, "CALLBACK": Lead.Status.CALLBACK}.get(attrs.get("call_outcome"))
        follow_up_at = attrs.get("follow_up_at")
        call_outcome = attrs.get("call_outcome")
        if call_outcome in CALL_OUTCOME_STATUS_OPTIONS:
            if next_status not in CALL_OUTCOME_STATUS_OPTIONS[call_outcome]:
                raise serializers.ValidationError({"status": "Choose a lead status that matches the call outcome."})
        if follow_up_at:
            if follow_up_at <= timezone.now():
                raise serializers.ValidationError({"follow_up_at": "Choose a future appointment time."})
            from datetime import timedelta
            if follow_up_at > timezone.now() + timedelta(days=3):
                raise serializers.ValidationError({"follow_up_at": "Follow-up cannot be scheduled more than 3 days in advance."})
        follow_up_statuses = [Lead.Status.RNR, Lead.Status.SWITCHED_OFF, Lead.Status.CALLBACK, Lead.Status.PENDING, Lead.Status.WALKIN]
        if next_status in [Lead.Status.CALLBACK, Lead.Status.PENDING, Lead.Status.WALKIN] and not follow_up_at:
            raise serializers.ValidationError({"follow_up_at": "This status requires a follow-up time."})
        if follow_up_at and next_status not in [None, Lead.Status.FRESH, *follow_up_statuses]:
            raise serializers.ValidationError({"follow_up_at": "Only callbacks and walk-ins can have an appointment."})
        return attrs


class AssignmentSerializer(serializers.Serializer):
    sales_officer_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role=User.Role.CRE, is_active=True, deleted_at__isnull=True), source="sales_officer")


class BulkDistributeSerializer(serializers.Serializer):
    sales_officer_ids = serializers.ListField(child=serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role=User.Role.CRE, is_active=True, deleted_at__isnull=True)), min_length=1)

    def validate_sales_officer_ids(self, officers):
        seen = set()
        unique = []
        for officer in officers:
            if officer.id not in seen:
                seen.add(officer.id)
                unique.append(officer)
        return unique


class PSAssignmentSerializer(serializers.Serializer):
    sales_officer_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role=User.Role.SALES_OFFICER, is_active=True, deleted_at__isnull=True), source="sales_officer")


class FollowUpSerializer(serializers.ModelSerializer):
    customer = serializers.CharField(source="lead.name", read_only=True)
    so_name = serializers.CharField(source="so.history_display_name", read_only=True)
    so_active = serializers.BooleanField(source="so.is_active", read_only=True)

    class Meta:
        model = FollowUp
        fields = ["id", "lead", "customer", "so_name", "so_active", "scheduled_for", "resolved_at", "notified_at", "reminder_held"]


class FollowUpReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["APPROVE", "RESOLVE"])
    scheduled_for = serializers.DateTimeField(required=False)

    def validate_scheduled_for(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Choose a future time when changing the schedule.")
        return value

class SystemConfigSerializer(serializers.ModelSerializer):
    def validate_lists(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Expected an object of lists.")
        sources = value.get("sources", [])
        if not isinstance(sources, list):
            raise serializers.ValidationError("Sources must be a list.")
        normalized = normalize_sources(sources)
        if any(len(source) > 100 for source in normalized):
            raise serializers.ValidationError("Each source must be 100 characters or fewer.")
        return {**value, "sources": normalized}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        lists = dict(data.get("lists") or {})
        lists["sources"] = normalize_sources(lists.get("sources", []))
        data["lists"] = lists
        return data

    class Meta:
        model = SystemConfig
        fields = ["lists", "updated_at"]
