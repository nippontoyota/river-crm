from rest_framework import serializers
from django.db import transaction
from .phone_lock import guard_manual_phone, lock_phones
from django.utils import timezone

from accounts.models import User
from .models import CallLog, FollowUp, Lead, LeadAudit, LeadQualification, SystemConfig
from .outcomes import PS_CALL_OUTCOME_STATUS_OPTIONS, outcome_policy, validate_sales_call
from .rtos import KERALA_RTO_CHOICES

SO_LEAD_SOURCES = ["Referral", "Existing customer", "Friends / Family", "Personal contact", "Local networking", "Self prospecting", "Other"]


def validate_so_source(value):
    if value not in SO_LEAD_SOURCES:
        raise serializers.ValidationError("Choose a source for an SO-generated lead.")
    return value


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


def validate_activity_pair(attrs, current=None):
    if not {"activity", "sub_activity"}.intersection(attrs):
        return attrs
    activity = attrs.get("activity", getattr(current, "activity", ""))
    sub_activity = attrs.get("sub_activity", getattr(current, "sub_activity", ""))
    if current and activity != current.activity and "sub_activity" not in attrs:
        attrs["sub_activity"] = sub_activity = ""
    if current and (activity, sub_activity) == (current.activity, current.sub_activity):
        return attrs  # Retired options remain editable on historical records.
    lists = SystemConfig.objects.filter(id=1).values_list("lists", flat=True).first() or {}
    if activity and activity not in lists.get("activities", []):
        raise serializers.ValidationError({"activity": "Choose an activity from Admin Lists."})
    if sub_activity and (not activity or sub_activity not in lists.get("subActivities", {}).get(activity, [])):
        raise serializers.ValidationError({"sub_activity": "Choose a sub-activity belonging to the selected activity."})
    return attrs



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

    def validate(self, attrs):
        if self.instance and any(field in attrs and attrs[field] != getattr(self.instance, field) for field in ("status", "sales_outcome")):
            raise serializers.ValidationError({"status": "Use the lead outcome update action to change sales progress."})
        if not self.instance and (attrs.get("status") == "WON" or attrs.get("sales_outcome") == "RETAILED"):
            raise serializers.ValidationError({"status": "Create the lead, register its chassis, then use the sales outcome action to mark it Retailed."})
        return validate_activity_pair(attrs, self.instance)

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
        if self.instance and self.instance.generated_by_id:
            return validate_so_source(value)
        return validate_configured_source(value, self.instance.source if self.instance else "")

    ps_officer_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role=User.Role.SALES_OFFICER, is_active=True, deleted_at__isnull=True), source="assigned_ps", required=False, write_only=True)

    class Meta:
        model = Lead
        fields = ["id", "uid", "name", "phone", "email", "source", "source_label", "campaign", "activity", "sub_activity", "test_drive_completed_at", "model_interest", "city", "rto", "branch", "enquiry_date", "status", "category", "sales_outcome", "assigned_so", "assigned_so_name", "assigned_ps", "assigned_ps_name", "generated_by", "ps_officer_id", "next_follow_up", "call_count", "qualification", "qualification_input", "flagged_to_manager", "needs_cre_reassignment", "needs_so_reassignment", "profession", "created_at", "updated_at"]
        read_only_fields = ["test_drive_completed_at", "uid", "assigned_so", "assigned_ps", "generated_by", "needs_cre_reassignment", "needs_so_reassignment", "created_at", "updated_at"]
        extra_kwargs = {"source": {"required": True}}

    @transaction.atomic
    def create(self, validated_data):
        guard_manual_phone(validated_data.get("phone", ""))
        qualification_data = validated_data.pop("qualification_input", None)
        lead = super().create(validated_data)
        if qualification_data:
            request = self.context.get("request")
            actor = request.user if request else None
            LeadQualification.objects.create(lead=lead, updated_by=actor, **qualification_data)
            LeadAudit.objects.create(lead=lead, actor=actor, event="qualification_updated", after=qualification_data)
        return lead

    def update(self, instance, validated_data):
        # These fields may be echoed by older detail forms, but only outcome
        # actions may write them (including when a detail form is stale).
        validated_data.pop("status", None)
        validated_data.pop("sales_outcome", None)
        from django.db import transaction
        def serial(value):
            return value.isoformat() if hasattr(value, "isoformat") else value.pk if hasattr(value, "pk") else value
        with transaction.atomic():
            if "phone" in validated_data and validated_data["phone"] != instance.phone:
                lock_phones(instance.phone, validated_data["phone"])
                guard_manual_phone(validated_data["phone"], instance.pk)
            instance = Lead.objects.select_for_update().get(pk=instance.pk)
            before = {key: serial(getattr(instance, key)) for key in validated_data if hasattr(instance, key)}
            updated = super().update(instance, validated_data)
            after = {key: serial(getattr(updated, key)) for key in before}
            request = self.context.get("request")
            if before != after:
                LeadAudit.objects.create(lead=updated, actor=request.user if request else None, event="details_updated", before=before, after=after)
            return updated


class SOLeadCreateSerializer(LeadSerializer):
    phone = serializers.RegexField(regex=r"^\d{10}$")

    def validate_source(self, value):
        return validate_so_source(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("model_interest"):
            raise serializers.ValidationError({"model_interest": "Choose a vehicle model."})
        if not attrs.get("enquiry_date"):
            raise serializers.ValidationError({"enquiry_date": "Enter the enquiry date."})
        if attrs.get("source") == "Other" and not attrs.get("source_label", "").strip():
            raise serializers.ValidationError({"source_label": "Describe how you found this customer."})
        return attrs

    class Meta(LeadSerializer.Meta):
        fields = [field for field in LeadSerializer.Meta.fields if field != "ps_officer_id"]
        read_only_fields = LeadSerializer.Meta.read_only_fields + ["branch", "status", "category", "sales_outcome"]


class SOLeadListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = ["id", "status", "name", "phone", "source", "flagged_to_manager"]


class LeadDetailSerializer(LeadSerializer):
    vehicles = serializers.SerializerMethodField()

    def get_vehicles(self, obj):
        return list(obj.vehicles.values("id", "chassis_number", "model", "registration_number"))

    outcome_policy = serializers.SerializerMethodField()
    whatsapp = serializers.SerializerMethodField()

    def get_whatsapp(self, obj):
        from notifications.models import WhatsAppContact
        from notifications.serializers import WhatsAppMessageSerializer
        from notifications.whatsapp import may_record_agreement, normalize_phone, whatsapp_mode
        request = self.context.get("request")
        contact = WhatsAppContact.objects.select_related("recorded_by").filter(lead=obj).first()
        return {
            "mode": whatsapp_mode(),
            "agreed": bool(contact and contact.agreed and contact.phone == normalize_phone(obj.phone)),
            "phone": contact.phone if contact else "",
            "recorded_at": contact.recorded_at if contact else None,
            "recorded_by": contact.recorded_by.history_display_name if contact and contact.recorded_by else None,
            "enrolled_at": contact.enrolled_at if contact else None,
            "can_record_agreement": may_record_agreement(request.user if request else None, obj),
            "messages": WhatsAppMessageSerializer(obj.whatsapp_messages.all()[:30], many=True).data,
        }

    def get_outcome_policy(self, obj):
        request = self.context.get("request")
        return outcome_policy(obj, request.user if request else None)

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
        fields = LeadSerializer.Meta.fields + ["vehicles", "call_history", "follow_up_history", "audit_history", "outcome_policy", "whatsapp"]


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
    whatsapp_agreed = serializers.BooleanField(required=False)
    activity = serializers.CharField(max_length=160, required=False, allow_blank=True)
    sub_activity = serializers.CharField(max_length=160, required=False, allow_blank=True)
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
        if self.context.get("self_generated"):
            return validate_so_source(value)
        return validate_configured_source(value, self.context.get("current_source", ""))

    def validate(self, attrs):
        attrs = validate_activity_pair(attrs, self.context.get("lead"))
        enquiry_date = attrs.get("enquiry_date")
        if enquiry_date and enquiry_date > timezone.localdate():
            raise serializers.ValidationError({"enquiry_date": "Enquiry date cannot be in the future."})
        user = self.context.get("user")
        if "whatsapp_agreed" in attrs:
            from notifications.whatsapp import may_record_agreement
            if not may_record_agreement(user, self.context["lead"]):
                raise serializers.ValidationError({"whatsapp_agreed": "Only the assigned CE or an administrator can record agreement."})
        if user and (user.role == User.Role.SALES_OFFICER or (user.is_admin and (attrs.get("call_status") or attrs.get("call_outcome") in PS_CALL_OUTCOME_STATUS_OPTIONS))):
            return validate_sales_call(self.context["lead"], user, attrs)
        if attrs.get("call_outcome") and attrs["call_outcome"] not in {"PENDING", "QUALIFIED", "LOST", "RNR", "SWITCHED_OFF", "CALLBACK", "Call Me Back", "Switch Off"}:
            raise serializers.ValidationError({"call_outcome": "Choose an outcome from your lead workflow."})
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
    rto_options = serializers.SerializerMethodField()
    so_lead_sources = serializers.SerializerMethodField()
    complaint_subtypes = serializers.SerializerMethodField()

    def get_complaint_subtypes(self, obj):
        from complaints.catalogue import COMPLAINT_SUBTYPES
        return COMPLAINT_SUBTYPES

    def get_so_lead_sources(self, obj):
        return SO_LEAD_SOURCES

    def get_rto_options(self, obj):
        return [{"value": code, "label": f"{code} - {name}"} for code, name in KERALA_RTO_CHOICES]

    def validate_lists(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Expected an object of lists.")
        sources = value.get("sources", [])
        if not isinstance(sources, list):
            raise serializers.ValidationError("Sources must be a list.")
        normalized = normalize_sources(sources)
        if any(len(source) > 100 for source in normalized):
            raise serializers.ValidationError("Each source must be 100 characters or fewer.")
        activities = value.get("activities", [])
        if not isinstance(activities, list) or any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 160 for item in activities):
            raise serializers.ValidationError("Activities must be non-empty names of at most 160 characters.")
        activities = list(dict.fromkeys(item.strip() for item in activities))
        sub_activities = value.get("subActivities", {})
        if not isinstance(sub_activities, dict):
            raise serializers.ValidationError("Sub-activities must be grouped by activity.")
        cleaned = {}
        for parent, children in sub_activities.items():
            if parent not in activities or not isinstance(children, list) or any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 160 for item in children):
                raise serializers.ValidationError("Each sub-activity must have a configured parent and a name of at most 160 characters.")
            cleaned[parent] = list(dict.fromkeys(item.strip() for item in children))
        return {**value, "sources": normalized, "activities": activities, "subActivities": cleaned}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        lists = dict(data.get("lists") or {})
        lists["sources"] = normalize_sources(lists.get("sources", []))
        data["lists"] = lists
        return data

    class Meta:
        model = SystemConfig
        fields = ["lists", "rto_options", "so_lead_sources", "complaint_subtypes", "updated_at"]
