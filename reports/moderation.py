"""Moderation of reported items.

Each action is one transaction: the report is locked, the item is hidden, the
report is closed and the audit entries are written together. A second click
cannot repeat it and nothing is left half done. Nothing is ever deleted.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from audit.services import record as record_audit
from notification.services import after_commit
from pets.notifications import notify_listing_rejected as notify_pet_rejected
from products.notifications import notify_listing_rejected as notify_product_rejected
from services.notifications import notify_listing_rejected as notify_service_rejected

from .models import Report
from .serializers import TARGET_MODELS

Kind = Report.ReportedItemType

LISTING_NOTIFIERS = {
    Kind.PET: notify_pet_rejected,
    Kind.PRODUCT: notify_product_rejected,
    Kind.SERVICE: notify_service_rejected,
}

REMOVED = "removed"
ALREADY_REMOVED = "already_removed"


def get_reported_item(report):
    """The reviewed thing itself, or None for a general report or a missing item."""
    if report.reported_item_type == Kind.GENERAL or report.reported_item_id is None:
        return None
    model = TARGET_MODELS[Kind(report.reported_item_type)]
    return model._base_manager.filter(pk=report.reported_item_id).first()


def _lock_pending(report_id):
    report = Report.objects.select_for_update().filter(pk=report_id).first()
    if report is None:
        raise NotFound("Report not found.")
    if report.status != Report.Status.PENDING:
        raise ValidationError({"report": "This report has already been handled."})
    return report


def _finish(report, new_status, admin, note):
    report.status = new_status
    report.reviewed_by = admin
    report.reviewed_at = timezone.now()
    report.resolution_note = note
    report.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "resolution_note",
            "updated_at",
        ]
    )


def _details(report):
    return {
        "item_type": report.reported_item_type,
        "item_id": report.reported_item_id,
    }


def close_report(report_id, admin, new_status, note=""):
    """Dismiss a report, or close a general one. Reports about an item are
    resolved only by removing the item."""
    with transaction.atomic():
        report = _lock_pending(report_id)
        if (
            new_status == Report.Status.RESOLVED
            and report.reported_item_type != Kind.GENERAL
        ):
            raise ValidationError(
                {"status": "Use the remove action to resolve a report about an item."}
            )
        _finish(report, new_status, admin, note)
        action = (
            "report.dismissed"
            if new_status == Report.Status.DISMISSED
            else "report.resolved"
        )
        record_audit(
            actor=admin, action=action, target=report, details=_details(report)
        )
    return report


def _hide_item(item, report, admin, reason):
    kind = Kind(report.reported_item_type)

    if kind == Kind.REVIEW:
        if not item.is_visible:
            return ALREADY_REMOVED
        item.is_visible = False
        item.save(update_fields=["is_visible", "updated_at"])
        record_audit(
            actor=admin,
            action="review.hidden",
            target=item,
            details={"report": report.pk},
        )
        return REMOVED

    # A listing: use the same fields the administrators' reject action sets.
    if not item.approved and item.rejection_reason:
        return ALREADY_REMOVED
    item.approved = False
    item.rejection_reason = reason
    item.reviewed_by = admin
    item.reviewed_at = timezone.now()
    item.save(
        update_fields=[
            "approved",
            "rejection_reason",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )
    record_audit(
        actor=admin,
        action=f"{kind.value.lower()}.rejected",
        target=item,
        details={"business": str(item.business_id), "report": report.pk},
    )
    notify = LISTING_NOTIFIERS[kind]
    after_commit(lambda: notify(item))
    return REMOVED


def remove_reported_item(report_id, admin, reason):
    """Hide the reported review or listing and resolve the report, together
    with any other pending reports about the same item."""
    with transaction.atomic():
        report = _lock_pending(report_id)
        if report.reported_item_type == Kind.GENERAL:
            raise ValidationError(
                {"report": "A general report has no item to remove. Dismiss it instead."}
            )
        item = get_reported_item(report)
        if item is None:
            raise ValidationError({"report": "The reported item no longer exists."})

        outcome = _hide_item(item, report, admin, reason)

        duplicate_ids = list(
            Report.objects.select_for_update()
            .filter(
                status=Report.Status.PENDING,
                reported_item_type=report.reported_item_type,
                reported_item_id=report.reported_item_id,
            )
            .exclude(pk=report.pk)
            .values_list("pk", flat=True)
        )
        if duplicate_ids:
            now = timezone.now()
            Report.objects.filter(pk__in=duplicate_ids).update(
                status=Report.Status.RESOLVED,
                reviewed_by=admin,
                reviewed_at=now,
                resolution_note=f"Resolved together with report {report.pk}.",
                updated_at=now,
            )

        _finish(report, Report.Status.RESOLVED, admin, reason)
        record_audit(
            actor=admin,
            action="report.resolved",
            target=report,
            details={
                **_details(report),
                "outcome": outcome,
                "also_resolved": duplicate_ids,
            },
        )
    return report
