from django.db import transaction

from audit.services import record  # adjust if your audit module is named differently

from .builders import BUILDERS
from .filters import parse_filters
from .models import SavedReport


def generate_report(report_type, raw_filters):
    """Validate the filters and compute the report live."""
    filters = parse_filters(report_type, raw_filters)
    return BUILDERS[report_type](filters)


def save_report(user, name, report_type, filters=None):
    """Compute a report now, freeze the result and log who saved it."""
    # The slow part runs outside the transaction, so it holds no locks.
    report = generate_report(report_type, filters or {})
    with transaction.atomic():
        saved = SavedReport.objects.create(
            name=name.strip(),
            report_type=report_type,
            filters=report["filters"],   # resolved filters, with real dates
            data=report,
            generated_by=user,
        )
        record(
            actor=user,
            action="report.saved",
            target=saved,
            details={"report_type": report_type, "filters": report["filters"]},
        )
    return saved


def record_export(user, report, fmt, saved=None):
    """Log a download. Exports carry user and revenue data, so they are tracked."""
    record(
        actor=user,
        action="report.exported",
        target=saved,
        details={
            "report_type": report["report"],
            "format": fmt,
            "filters": report["filters"],
            "saved_report": saved is not None,
        },
    )