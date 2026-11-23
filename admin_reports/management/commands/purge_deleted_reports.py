from django.core.management.base import BaseCommand
from django.db import transaction

from audit.services import record
from admin_reports.models import SavedReport


class Command(BaseCommand):
    help = "Permanently delete saved reports trashed for more than 30 days."

    def handle(self, *args, **options):
        purged = 0
        expired = (
            SavedReport.all_objects.expired()
            .select_related("generated_by")
            .defer("data")
        )
        for report in expired.iterator():
            with transaction.atomic():
                # Each permanent deletion leaves its own audit entry.
                record(
                    actor=None,
                    action="report.purged",
                    target=report,
                    details={
                        "name": report.name,
                        "report_type": report.report_type,
                        "saved_by": (
                            report.generated_by.email
                            if report.generated_by else ""
                        ),
                        "deleted_at": report.deleted_at.isoformat(),
                    },
                )
                report.delete()
            purged += 1
        self.stdout.write(f"Permanently deleted {purged} expired report(s).")