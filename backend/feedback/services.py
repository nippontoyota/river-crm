from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count
from django.db.models.functions import Lower, Trim
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User
from notifications.models import Notification
from .models import FeedbackAssignment, FeedbackAttempt, FeedbackIssue, FeedbackIssueEvent, FeedbackState, FeedbackTask
from .questionnaires import CURRENT_VERSION, QUESTIONNAIRES


def branch_key(value):
    return (value or "").strip().casefold()


def morning_after(moment, days=1):
    return timezone.make_aware(datetime.combine(timezone.localdate(moment) + timedelta(days=days), time(9)))


def lock_feedback():
    # ponytail: one database lock serializes feedback writes; use per-branch locks if volume warrants it.
    return FeedbackState.objects.select_for_update().get(pk=1)


def eligible_callers():
    return User.objects.filter(role=User.Role.FEEDBACK, is_active=True, deleted_at__isnull=True)


def notify(task, kind, message):
    # The task supplies the customer link. A second lead FK would acquire a source
    # row lock at commit, reversing source → feedback lock ordering.
    if task.assigned_to_id:
        Notification.objects.get_or_create(dedupe_key=f"feedback:{task.pk}:{task.revision}:{kind}", defaults={
            "user_id": task.assigned_to_id, "feedback_task": task,
            "kind": kind, "message": f"{task.kind} · {task.customer[:120]} · {message}"})


def assign(task, caller, branch, reason, actor=None):
    if task.assigned_to_id == (caller.pk if caller else None) and task.branch == branch:
        return
    FeedbackAssignment.objects.create(task=task, actor=actor, previous_owner_id=task.assigned_to_id,
        assigned_to=caller, previous_branch=task.branch, branch=branch, reason=reason)
    Notification.objects.filter(feedback_task=task).delete()
    task.assigned_to = caller
    task.branch = branch
    task.revision += 1
    task.save(update_fields=["assigned_to", "branch", "revision"])
    notify(task, "FEEDBACK_ASSIGNED", "Assigned to you")


def allocate(task, reason="Automatic assignment", actor=None):
    branch = branch_key(task.source_branch)
    loads = dict(FeedbackTask.objects.filter(status="OPEN", assigned_to__isnull=False,
        lead__deleted_at__isnull=True).values("assigned_to_id").annotate(n=Count("id")).values_list("assigned_to_id", "n"))
    callers = list(eligible_callers())
    caller = next((user for user in callers if user.pk == task.assigned_to_id), None)
    if not caller:
        caller = min(callers, key=lambda user: (loads.get(user.id, 0), user.id)) if callers else None
    assign(task, caller, branch, reason, actor)


@transaction.atomic
def reconcile_assignments():
    lock_feedback()
    tasks = FeedbackTask.objects.filter(status="OPEN", lead__deleted_at__isnull=True).select_related("lead", "assigned_to", "service_event__request").order_by("original_due_at", "id")
    for task in tasks:
        user = task.assigned_to
        branch = branch_key(task.source_branch)
        if task.branch != branch or not user or not user.is_active or user.deleted_at or user.role != "FEEDBACK":
            allocate(task, "Branch or staffing changed")


@transaction.atomic
def record_audit(audit):
    kind = None
    lead = audit.lead
    if audit.event == "test_drive_completed" and lead.test_drive_completed_at:
        kind = "TDF"
    elif audit.event in {"so_updated", "status_changed"}:
        before, after = audit.before.get("sales_outcome"), audit.after.get("sales_outcome")
        if before != after:
            kind = {"BOOKED": "PBF", "RETAILED": "PSF"}.get(after)
    branch_changed = "branch" in audit.after and audit.before.get("branch") != audit.after["branch"]
    if not kind and not branch_changed:
        return
    state = lock_feedback()
    if branch_changed:
        for task in FeedbackTask.objects.filter(lead=lead, status="OPEN").select_related("lead"):
            if task.branch != branch_key(lead.branch):
                allocate(task, "Lead branch changed", audit.actor)
    if not kind or audit.created_at < state.activated_at or lead.deleted_at:
        return
    occurred_at = lead.test_drive_completed_at if kind == "TDF" else audit.created_at
    if occurred_at < state.activated_at:
        return
    due = morning_after(occurred_at, 3 if kind == "PSF" else 1)
    task, created = FeedbackTask.objects.get_or_create(lead=lead, kind=kind, defaults={
        "questionnaire_version": CURRENT_VERSION, "source_audit": audit, "branch": branch_key(lead.branch), "occurred_at": occurred_at,
        "original_due_at": due, "next_call_at": due})
    if created:
        allocate(task)


@transaction.atomic
def save_attempt(task_id, user, data):
    lock_feedback()
    task = FeedbackTask.objects.select_related("lead", "assigned_to", "service_event__request").get(pk=task_id)
    current_user = User.objects.get(pk=user.pk)
    if not current_user.is_active or current_user.deleted_at or current_user.role != "FEEDBACK" or task.assigned_to_id != user.pk or (task.lead_id and task.lead.deleted_at):
        raise PermissionDenied("This feedback task is no longer assigned to you.")
    if task.status != "OPEN" or task.revision != data["revision"]:
        raise ValidationError("This task changed. Refresh before recording a call.")
    now = timezone.now()
    if task.next_call_at > now:
        raise ValidationError("This call is not due yet.")
    callback = data.get("callback_at")
    if data["outcome"] == "CALLBACK" and (not callback or callback <= now):
        raise ValidationError({"callback_at": "Choose a future callback time."})
    outcome = data["outcome"]
    if outcome == "COLLECTED":
        record_answers(task, data)
    FeedbackAttempt.objects.create(task=task, caller=current_user, branch=task.branch, outcome=outcome,
        notes=data.get("notes", ""), scheduled_for=task.next_call_at, callback_at=callback, created_at=now)
    if outcome == "COLLECTED":
        task.status, task.completed_at = "COMPLETED", now
        task.on_time = None if task.origin == "HISTORICAL" else timezone.localdate(now) <= timezone.localdate(task.original_due_at)
    elif outcome in {"DECLINED", "INVALID_NUMBER"}:
        task.status = outcome
    elif outcome == "CALLBACK":
        task.next_call_at = callback
    else:
        task.unsuccessful_attempts += 1
        if task.unsuccessful_attempts >= 3:
            task.status = "UNREACHABLE"
        else:
            task.next_call_at = morning_after(now)
    if task.status != "OPEN":
        task.closed_at = now
    task.revision += 1
    task.save()
    Notification.objects.filter(feedback_task=task, read_at__isnull=True).update(read_at=now)
    if outcome == "COLLECTED":
        reasons = []
        if task.satisfaction is not None and task.satisfaction <= 2:
            reasons.append("Low satisfaction rating")
        if task.further_help:
            reasons.append(task.help_details)
        if task.kind == "SVC" and task.answers.get("issue_resolved") == "NO":
            reasons.append("Service issue remains unresolved")
        if reasons:
            ensure_issue(task, "; ".join(reasons), current_user)
    return task


def record_answers(task, data):
    # Legacy tasks can still be completed by the old notes-only client.
    if not task.questionnaire_version and "answers" not in data:
        return
    version = task.questionnaire_version or CURRENT_VERSION
    answers = data.get("answers")
    expected = QUESTIONNAIRES[version][task.kind]
    if not isinstance(answers, dict) or set(answers) != set(expected) or any(value not in ("YES", "NO", "NOT_DISCUSSED") for value in answers.values()):
        raise ValidationError({"answers": "Answer each stage question with Yes, No or Not discussed."})
    if "satisfaction" not in data or "further_help" not in data:
        raise ValidationError("Record satisfaction (or Not provided) and whether further help is needed.")
    if data["further_help"] and not data.get("help_details", "").strip():
        raise ValidationError({"help_details": "Describe the help needed."})
    task.questionnaire_version = version
    task.answers = answers
    task.satisfaction = data["satisfaction"]
    task.further_help = data["further_help"]
    task.help_details = data.get("help_details", "") if task.further_help else ""


@transaction.atomic
def record_service_event(event):
    """Called inside the service transaction: service rows precede the feedback lock.

    Feedback mutations never lock service/lead/user rows after the allocation lock.
    """
    if event.action not in {"resolve", "reopen"}:
        return
    state = lock_feedback()
    request = event.request
    if event.action == "reopen":
        for task in FeedbackTask.objects.filter(service_event__request=request, status="OPEN"):
            task.status = "CANCELLED"
            task.cancellation_reason = f"Service request reopened: {event.note}"
            task.closed_at = event.created_at
            task.revision += 1
            task.save(update_fields=["status", "cancellation_reason", "closed_at", "revision"])
            Notification.objects.filter(feedback_task=task, read_at__isnull=True).update(read_at=event.created_at)
        return
    if event.created_at < state.activated_at or event.before.get("status") == "RESOLVED" or event.after.get("status") != "RESOLVED":
        return
    due = morning_after(event.created_at)
    task, created = FeedbackTask.objects.get_or_create(service_event=event, defaults={
        "kind": "SVC", "branch": branch_key(request.branch), "occurred_at": event.created_at,
        "original_due_at": due, "next_call_at": due, "questionnaire_version": CURRENT_VERSION})
    if created:
        allocate(task)


def notify_issue(issue):
    managers = User.objects.filter(role="SALES_MANAGER", is_active=True, deleted_at__isnull=True).annotate(
        branch_key=Lower(Trim("location"))).filter(branch_key=issue.task.branch) if issue.task.branch else User.objects.none()
    overdue = not issue.acknowledged_at and issue.created_at <= timezone.now() - timedelta(hours=24)
    recipients = list(managers)
    if not recipients or overdue:
        recipients += list(User.objects.filter(role="ADMIN", is_active=True, deleted_at__isnull=True))
    for user in recipients:
        Notification.objects.get_or_create(dedupe_key=f"feedback-issue:{issue.pk}:{user.pk}", defaults={
            "user": user, "feedback_task": issue.task,
            "kind": "FEEDBACK_ISSUE", "message": f"Feedback needs attention · {issue.task.customer[:120]}"})


def ensure_issue(task, reason, actor):
    issue, created = FeedbackIssue.objects.get_or_create(task=task, defaults={"reason": reason})
    if created:
        FeedbackIssueEvent.objects.create(issue=issue, actor=actor, status="OPEN", note=reason)
        notify_issue(issue)
    return issue


def change_issue(issue, status, actor, note):
    now = timezone.now()
    issue.status = status
    if not issue.acknowledged_at:
        issue.acknowledged_at, issue.acknowledged_by = now, actor
    if status == "RESOLVED":
        issue.resolved_at, issue.resolved_by, issue.resolution_notes = now, actor, note
    issue.save()
    FeedbackIssueEvent.objects.create(issue=issue, actor=actor, status=status, note=note)
    issue.task.revision += 1
    issue.task.save(update_fields=["revision"])
    Notification.objects.filter(feedback_task=issue.task, kind="FEEDBACK_ISSUE", read_at__isnull=True).update(read_at=now)


@transaction.atomic
def resolve_complaint_issue(complaint, actor):
    if complaint.status not in {"RESOLVED", "CLOSED"}:
        return
    lock_feedback()
    issue = FeedbackIssue.objects.select_related("task").filter(complaint=complaint).exclude(status="RESOLVED").first()
    if issue:
        change_issue(issue, "RESOLVED", actor, complaint.resolution_notes)
