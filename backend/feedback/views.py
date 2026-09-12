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
from .models import FeedbackState
from .permissions import FeedbackPermission, visible_tasks
from .reporting import task_query, report
from .serializers import AttemptInput, ReassignInput, TaskDetailSerializer, TaskSerializer
from .services import assign, branch_key, eligible_callers, lock_feedback, save_attempt


class FeedbackViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    permission_classes = [FeedbackPermission]
    serializer_class = TaskSerializer

    def get_queryset(self):
        queryset = task_query(self.request.user, self.request.query_params,
            period=self.request.query_params.get("backlog") != "true") if self.action in {"list", "export"} else visible_tasks(self.request.user)
        return queryset.select_related("lead", "lead__assigned_so", "lead__assigned_ps", "assigned_to").order_by("next_call_at", "id")

    def get_serializer_class(self):
        return TaskDetailSerializer if self.action == "retrieve" else TaskSerializer

    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(report(request.user, request.query_params))

    @action(detail=False, methods=["get"])
    def options(self, request):
        user = request.user
        callers = User.objects.filter(role="FEEDBACK").order_by("first_name", "id")
        branches = set(Lead.objects.exclude(branch="").values_list("branch", flat=True))
        branches.update(visible_tasks(user).exclude(branch="").values_list("branch", flat=True))
        if user.role in {"FEEDBACK", "SALES_MANAGER"}:
            callers = callers.filter(id__in=eligible_callers(branch_key(user.location)).values("id"))
            branches = {user.location} if branch_key(user.location) else set()
        if user.role == "FEEDBACK":
            callers = callers.filter(pk=user.pk)
        state = FeedbackState.objects.get(pk=1)
        return Response({"branches": sorted({branch_key(b) for b in branches if branch_key(b)}),
            "callers": [{"id": c.pk, "name": c.history_display_name, "branch": branch_key(c.location), "active": c.is_active and not c.deleted_at} for c in callers],
            "activated_at": state.activated_at})

    @action(detail=True, methods=["post"])
    def attempt(self, request, pk=None):
        task = self.get_object()
        serializer = AttemptInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = save_attempt(task.pk, request.user, serializer.validated_data)
        return Response(TaskDetailSerializer(result).data)

    @action(detail=True, methods=["post"])
    def reassign(self, request, pk=None):
        serializer = ReassignInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            lock_feedback()
            task = self.get_object()
            if task.status != "OPEN" or task.revision != serializer.validated_data["revision"]:
                raise ValidationError("This task changed. Refresh before reassigning.")
            branch = branch_key(task.lead.branch)
            caller = get_object_or_404(eligible_callers(branch), pk=serializer.validated_data["assigned_to"])
            assign(task, caller, branch, "Manual reassignment", request.user)
            return Response(TaskDetailSerializer(task).data)

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
