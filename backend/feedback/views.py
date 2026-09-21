import csv
import io

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from accounts.models import User
from leads.models import Lead
from .models import FeedbackIssue, FeedbackIssueEvent, FeedbackState
from .permissions import FeedbackPermission, visible_tasks
from .reporting import task_query, report
from .serializers import ComplaintInput, IssueInput, AttemptInput, ReassignInput, TaskDetailSerializer, TaskSerializer
from .services import change_issue, ensure_issue, assign, branch_key, eligible_callers, lock_feedback, save_attempt


class FeedbackViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    permission_classes = [FeedbackPermission]
    serializer_class = TaskSerializer

    def get_queryset(self):
        queryset = task_query(self.request.user, self.request.query_params,
            period=self.request.query_params.get("backlog") != "true") if self.action in {"list", "export"} else visible_tasks(self.request.user)
        return queryset.select_related("lead", "lead__assigned_so", "lead__assigned_ps", "assigned_to", "service_event__request__vehicle", "manual_request", "issue__complaint").order_by("next_call_at", "id")

    def get_serializer_class(self):
        return TaskDetailSerializer if self.action == "retrieve" else TaskSerializer

    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(report(request.user, request.query_params))

    @action(detail=False, methods=["get"])
    def options(self, request):
        from complaints.models import Complaint
        from complaints.catalogue import COMPLAINT_SUBTYPES
        from .questionnaires import QUESTIONNAIRES
        user = request.user
        callers = User.objects.filter(role="FEEDBACK").order_by("first_name", "id")
        branches = set(Lead.objects.exclude(branch="").values_list("branch", flat=True))
        branches.update(visible_tasks(user).exclude(branch="").values_list("branch", flat=True))
        if user.role == "SALES_MANAGER":
            branches = {user.location} if branch_key(user.location) else set()
        if user.role == "FEEDBACK":
            callers = callers.filter(pk=user.pk)
            branches = set()
        state = FeedbackState.objects.get(pk=1)
        return Response({"branches": sorted({branch_key(b) for b in branches if branch_key(b)}),
            "callers": [{"id": c.pk, "name": c.history_display_name, "active": c.is_active and not c.deleted_at} for c in callers],
            "activated_at": state.activated_at, "questionnaires": QUESTIONNAIRES, "complaint_categories": dict(Complaint.Category.choices), "complaint_subtypes": COMPLAINT_SUBTYPES})

    @action(detail=True, methods=["post"])
    def attempt(self, request, pk=None):
        task = self.get_object()
        serializer = AttemptInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = save_attempt(task.pk, request.user, serializer.validated_data)
        return Response(TaskDetailSerializer(result, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def reassign(self, request, pk=None):
        serializer = ReassignInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            lock_feedback()
            task = self.get_object()
            if task.status != "OPEN" or task.revision != serializer.validated_data["revision"]:
                raise ValidationError("This task changed. Refresh before reassigning.")
            branch = branch_key(task.source_branch)
            caller = get_object_or_404(eligible_callers(), pk=serializer.validated_data["assigned_to"])
            assign(task, caller, branch, "Manual reassignment", request.user)
            return Response(TaskDetailSerializer(task, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def issue(self, request, pk=None):
        data = IssueInput(data=request.data)
        data.is_valid(raise_exception=True)
        lock_feedback()
        task = self.get_object()
        values = data.validated_data
        if task.revision != values["revision"]:
            raise ValidationError("This task changed. Refresh before reviewing it.")
        issue = get_object_or_404(FeedbackIssue, task=task)
        if issue.status == "RESOLVED" or (issue.status == "ACKNOWLEDGED" and values["status"] == "ACKNOWLEDGED"):
            raise ValidationError("This issue has already been reviewed.")
        if values["status"] == "RESOLVED" and issue.complaint_id and issue.complaint.status not in {"RESOLVED", "CLOSED"}:
            raise ValidationError("The Complaints department must resolve the linked ticket first.")
        change_issue(issue, values["status"], request.user, values["notes"])
        return Response(TaskDetailSerializer(self.get_object(), context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def complaint(self, request, pk=None):
        from complaints.models import Complaint
        from ceo.tracking import complaint_event
        data = ComplaintInput(data=request.data)
        data.is_valid(raise_exception=True)
        source_task = self.get_object()
        lead_id = source_task.lead_id or source_task.service_event.request.vehicle.related_lead_id
        # Complaint and reporting FKs need the source lock before feedback allocation.
        if lead_id:
            Lead.objects.select_for_update().get(pk=lead_id)
        lock_feedback()
        task = self.get_object()
        values = data.validated_data
        # A retry returns the original ticket, even if the successful write advanced the revision.
        if FeedbackIssue.objects.filter(task=task, complaint__isnull=False).exists():
            return Response(TaskDetailSerializer(task, context=self.get_serializer_context()).data)
        if task.revision != values["revision"] or task.status != "COMPLETED":
            raise ValidationError("Complete the feedback call and refresh before raising a complaint.")
        issue = ensure_issue(task, "Caller raised a complaint", request.user)
        if issue.status == "RESOLVED":
            raise ValidationError("This feedback issue is already resolved.")
        complaint = Complaint.objects.create(ticket_number=f"CMP-F{task.pk:010d}", logged_by=request.user,
            related_lead_id=task.lead_id or task.service_event.request.vehicle.related_lead_id,
            customer_name=task.customer, customer_phone=task.phone, model_interest=task.model, branch=task.branch,
            category=values["category"], subtype=values["subtype"], description=values["description"],
            subject=f"{task.kind} feedback · {task.customer}"[:200])
        issue.complaint = complaint
        issue.save(update_fields=["complaint"])
        FeedbackIssueEvent.objects.create(issue=issue, actor=request.user, status=issue.status, note=f"Raised {complaint.ticket_number}: {values['description']}")
        complaint_event(complaint, request.user, "complaint_created")
        task.revision += 1
        task.save(update_fields=["revision"])
        return Response(TaskDetailSerializer(self.get_object(), context=self.get_serializer_context()).data, status=201)

    @action(detail=False, methods=["get"], url_path="historical-preview")
    def historical_preview(self, request):
        from .historical import preview
        return Response(preview())

    @action(detail=False, methods=["post"], url_path="historical-import")
    def historical_import(self, request):
        from .historical import HistoricalInput, import_selected
        data = HistoricalInput(data=request.data)
        data.is_valid(raise_exception=True)
        tasks = import_selected(data.validated_data, request.user)
        return Response(TaskSerializer(tasks, many=True).data)

    @action(detail=False, methods=["get"])
    def export(self, request):
        output = io.StringIO()
        writer = csv.writer(output)
        fields = TaskSerializer.Meta.fields
        writer.writerow(fields)
        for task in self.get_queryset().iterator(chunk_size=500):
            row = TaskSerializer(task).data
            # Customer-entered cells must stay text when opened in spreadsheet applications.
            writer.writerow([("'" + str(row[key])) if str(row[key]).lstrip().startswith(("=", "+", "-", "@")) else row[key] for key in fields])
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="feedback-tasks.csv"'
        return response
