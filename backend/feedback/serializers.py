from rest_framework import serializers

from .models import FeedbackAssignment, FeedbackAttempt, FeedbackTask


class AttemptInput(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    outcome = serializers.ChoiceField(choices=FeedbackAttempt.Outcome.choices)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    callback_at = serializers.DateTimeField(required=False, allow_null=True)

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
    customer = serializers.CharField(source="lead.name")
    phone = serializers.CharField(source="lead.phone")
    model = serializers.CharField(source="lead.model_interest")
    lead_branch = serializers.CharField(source="lead.branch")
    lead_status = serializers.CharField(source="lead.status")
    sales_outcome = serializers.CharField(source="lead.sales_outcome")
    cre_name = serializers.CharField(source="lead.assigned_so.history_display_name", default="Unassigned")
    so_name = serializers.CharField(source="lead.assigned_ps.history_display_name", default="Unassigned")
    caller_name = serializers.CharField(source="assigned_to.history_display_name", default="Unassigned")

    class Meta:
        model = FeedbackTask
        fields = ["id", "lead", "customer", "phone", "model", "lead_branch", "lead_status", "sales_outcome", "cre_name", "so_name",
            "kind", "branch", "assigned_to", "caller_name", "status", "occurred_at", "original_due_at", "next_call_at",
            "unsuccessful_attempts", "completed_at", "closed_at", "on_time", "revision", "created_at"]


class TaskDetailSerializer(TaskSerializer):
    attempts = AttemptSerializer(many=True)
    assignments = AssignmentSerializer(many=True)

    class Meta(TaskSerializer.Meta):
        fields = TaskSerializer.Meta.fields + ["attempts", "assignments"]
