from rest_framework import serializers

from .models import FeedbackAssignment, FeedbackAttempt, FeedbackIssue, FeedbackIssueEvent, FeedbackTask
from .questionnaires import CURRENT_VERSION, QUESTIONNAIRES


class AttemptInput(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    outcome = serializers.ChoiceField(choices=FeedbackAttempt.Outcome.choices)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    callback_at = serializers.DateTimeField(required=False, allow_null=True)

    satisfaction = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    answers = serializers.DictField(child=serializers.ChoiceField(choices=["YES", "NO", "NOT_DISCUSSED"]), required=False)
    further_help = serializers.BooleanField(required=False)
    help_details = serializers.CharField(required=False, allow_blank=True, max_length=5000)

    def validate(self, attrs):
        if attrs["outcome"] in {"COLLECTED", "DECLINED", "INVALID_NUMBER"} and not attrs.get("notes", "").strip():
            raise serializers.ValidationError({"notes": "Record the feedback or closure reason."})
        if attrs["outcome"] != "CALLBACK" and attrs.get("callback_at"):
            raise serializers.ValidationError({"callback_at": "Only requested callbacks may set a callback time."})
        return attrs


class ReassignInput(serializers.Serializer):
    assigned_to = serializers.IntegerField(min_value=1)
    revision = serializers.IntegerField(min_value=0)


class AttemptSerializer(serializers.ModelSerializer):
    caller_name = serializers.CharField(source="caller.history_display_name")

    class Meta:
        model = FeedbackAttempt
        fields = ["id", "caller", "caller_name", "branch", "outcome", "notes", "scheduled_for", "callback_at", "created_at"]


class AssignmentSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.history_display_name", default="System")
    previous_owner_name = serializers.CharField(source="previous_owner.history_display_name", default="Unassigned")
    assigned_to_name = serializers.CharField(source="assigned_to.history_display_name", default="Unassigned")

    class Meta:
        model = FeedbackAssignment
        fields = ["id", "actor_name", "previous_owner_name", "assigned_to_name", "previous_branch", "branch", "reason", "created_at"]


class TaskSerializer(serializers.ModelSerializer):
    customer = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    model = serializers.CharField(read_only=True)
    lead_branch = serializers.CharField(source="source_branch")
    lead_status = serializers.CharField(source="lead.status", default="")
    sales_outcome = serializers.CharField(source="lead.sales_outcome", default="")
    cre_name = serializers.CharField(source="lead.assigned_so.history_display_name", default="Unassigned")
    so_name = serializers.CharField(source="lead.assigned_ps.history_display_name", default="Unassigned")
    caller_name = serializers.CharField(source="assigned_to.history_display_name", default="Unassigned")

    unassigned_reason = serializers.SerializerMethodField()
    issue_status = serializers.CharField(source="issue.status", default=None)
    complaint_ticket = serializers.CharField(source="issue.complaint.ticket_number", default=None)
    complaint_status = serializers.CharField(source="issue.complaint.status", default=None)
    service_ticket = serializers.CharField(source="service_event.request.ticket_number", default=None)
    request_reason = serializers.CharField(source="manual_request.reason", default="")

    def get_unassigned_reason(self, obj):
        if obj.status != "OPEN" or obj.assigned_to_id:
            return ""
        return "No active feedback caller"

    class Meta:
        model = FeedbackTask
        fields = ["id", "lead", "customer", "phone", "model", "lead_branch", "lead_status", "sales_outcome", "cre_name", "so_name",
            "kind", "branch", "assigned_to", "caller_name", "status", "occurred_at", "original_due_at", "next_call_at",
            "unsuccessful_attempts", "completed_at", "closed_at", "on_time", "revision", "created_at",
            "origin", "cancellation_reason", "service_ticket", "request_reason", "unassigned_reason", "questionnaire_version", "answers", "satisfaction", "further_help", "help_details", "issue_status", "complaint_ticket", "complaint_status"]


class IssueEventSerializer(serializers.ModelSerializer):
    reviewer = serializers.CharField(source="actor.history_display_name", default="System")

    class Meta:
        model = FeedbackIssueEvent
        fields = ["status", "reviewer", "note", "created_at"]


class IssueSerializer(serializers.ModelSerializer):
    events = IssueEventSerializer(many=True)
    acknowledged_by_name = serializers.CharField(source="acknowledged_by.history_display_name", default=None)
    resolved_by_name = serializers.CharField(source="resolved_by.history_display_name", default=None)

    class Meta:
        model = FeedbackIssue
        fields = ["status", "reason", "acknowledged_at", "acknowledged_by_name", "resolved_at", "resolved_by_name", "resolution_notes", "events"]


class TaskDetailSerializer(TaskSerializer):
    attempts = AttemptSerializer(many=True)
    assignments = AssignmentSerializer(many=True)
    issue = IssueSerializer(read_only=True, default=None)
    questions = serializers.SerializerMethodField()
    contact_history = serializers.SerializerMethodField()
    other_open_tasks = serializers.SerializerMethodField()
    service = serializers.SerializerMethodField()

    def get_questions(self, obj):
        return QUESTIONNAIRES[obj.questionnaire_version or CURRENT_VERSION][obj.kind]

    def related_tasks(self, obj):
        from django.db.models import Q
        from .permissions import visible_tasks
        user = self.context["request"].user
        related = Q(lead_id=obj.lead_id) if obj.lead_id else Q(service_event__request__vehicle_id=obj.service_event.request.vehicle_id)
        lead_id = obj.lead_id or obj.service_event.request.vehicle.related_lead_id
        if lead_id:
            related |= Q(lead_id=lead_id) | Q(service_event__request__vehicle__related_lead_id=lead_id)
        return visible_tasks(user).filter(related)

    def get_contact_history(self, obj):
        attempts = FeedbackAttempt.objects.filter(task__in=self.related_tasks(obj)).select_related("caller", "task").order_by("-created_at", "-id")
        return [{**AttemptSerializer(attempt).data, "task": attempt.task_id, "kind": attempt.task.kind} for attempt in attempts]

    def get_other_open_tasks(self, obj):
        return list(self.related_tasks(obj).filter(status="OPEN").exclude(pk=obj.pk).values("id", "kind", "next_call_at"))

    def get_service(self, obj):
        if not obj.service_event_id:
            return None
        row = obj.service_event.request
        return {"ticket": row.ticket_number, "status": row.status, "vehicle": row.vehicle_snapshot,
            "issue": row.issue, "resolution_notes": obj.service_event.note}


    class Meta(TaskSerializer.Meta):
        fields = TaskSerializer.Meta.fields + ["attempts", "assignments", "issue", "questions", "contact_history", "other_open_tasks", "service"]


class IssueInput(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=["ACKNOWLEDGED", "RESOLVED"])
    notes = serializers.CharField(max_length=5000)


class ComplaintInput(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    category = serializers.CharField()
    subtype = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=5000)
    confirmed = serializers.BooleanField()

    def validate(self, attrs):
        from complaints.catalogue import COMPLAINT_SUBTYPES
        if not attrs["confirmed"]:
            raise serializers.ValidationError({"confirmed": "Confirm the complaint description before raising it."})
        if attrs["subtype"] not in COMPLAINT_SUBTYPES.get(attrs["category"], []):
            raise serializers.ValidationError({"subtype": "Choose a subtype belonging to this category."})
        return attrs
