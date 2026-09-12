from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count
from django.db.models.functions import Lower, Trim
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User
from notifications.models import Notification
from .models import FeedbackAssignment, FeedbackAttempt, FeedbackState, FeedbackTask


def branch_key(value):
    return (value or "").strip().casefold()


def morning_after(moment, days=1):
    return timezone.make_aware(datetime.combine(timezone.localdate(moment) + timedelta(days=days), time(9)))


def lock_feedback():
    # ponytail: one database lock serializes feedback writes; use per-branch locks if volume warrants it.
    return FeedbackState.objects.select_for_update().get(pk=1)


def eligible_callers(branch):
    return User.objects.filter(role=User.Role.FEEDBACK, is_active=True, deleted_at__isnull=True).annotate(
        branch_key=Lower(Trim("location"))).filter(branch_key=branch) if branch else User.objects.none()


def notify(task, kind, message):
    if task.assigned_to_id:
        Notification.objects.get_or_create(dedupe_key=f"feedback:{task.pk}:{task.revision}:{kind}", defaults={
            "user_id": task.assigned_to_id, "lead_id": task.lead_id, "feedback_task": task,
            "kind": kind, "message": f"{task.kind} · {task.lead.name[:120]} · {message}"})


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
    branch = branch_key(task.lead.branch)
    loads = dict(FeedbackTask.objects.filter(status="OPEN", assigned_to__isnull=False,
        lead__deleted_at__isnull=True).values("assigned_to_id").annotate(n=Count("id")).values_list("assigned_to_id", "n"))
    callers = list(eligible_callers(branch))
    caller = min(callers, key=lambda user: (loads.get(user.id, 0), user.id)) if callers else None
    assign(task, caller, branch, reason, actor)


@transaction.atomic
def reconcile_assignments():
    lock_feedback()
    tasks = FeedbackTask.objects.filter(status="OPEN", lead__deleted_at__isnull=True).select_related("lead", "assigned_to").order_by("original_due_at", "id")
    for task in tasks:
        user = task.assigned_to
        branch = branch_key(task.lead.branch)
        if task.branch != branch or not user or not user.is_active or user.deleted_at or user.role != "FEEDBACK" or branch_key(user.location) != branch:
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
        "source_audit": audit, "branch": branch_key(lead.branch), "occurred_at": occurred_at,
        "original_due_at": due, "next_call_at": due})
    if created:
        allocate(task)


@transaction.atomic
def save_attempt(task_id, user, data):
    lock_feedback()
    task = FeedbackTask.objects.select_related("lead", "assigned_to").get(pk=task_id)
    current_user = User.objects.get(pk=user.pk)
    if not current_user.is_active or current_user.deleted_at or current_user.role != "FEEDBACK" or task.assigned_to_id != user.pk or not task.branch or task.branch != branch_key(current_user.location) or task.branch != branch_key(task.lead.branch) or task.lead.deleted_at:
        raise PermissionDenied("This feedback task is no longer assigned to you in your branch.")
    if task.status != "OPEN" or task.revision != data["revision"]:
        raise ValidationError("This task changed. Refresh before recording a call.")
    now = timezone.now()
    if task.next_call_at > now:
        raise ValidationError("This call is not due yet.")
    callback = data.get("callback_at")
    if data["outcome"] == "CALLBACK" and (not callback or callback <= now):
        raise ValidationError({"callback_at": "Choose a future callback time."})
    outcome = data["outcome"]
    FeedbackAttempt.objects.create(task=task, caller=current_user, branch=task.branch, outcome=outcome,
        notes=data.get("notes", ""), scheduled_for=task.next_call_at, callback_at=callback, created_at=now)
    if outcome == "COLLECTED":
        task.status, task.completed_at = "COMPLETED", now
        task.on_time = timezone.localdate(now) <= timezone.localdate(task.original_due_at)
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
    return task
