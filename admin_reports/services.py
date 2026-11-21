from .builders import BUILDERS
from .filters import parse_filters
from .models import SavedReport


def generate_report(report_type, raw_filters):
    """Validate the filters and compute the report live."""
    filters = parse_filters(report_type, raw_filters)
    return BUILDERS[report_type](filters)


def save_report(user, name, report_type, filters=None):
    """Compute a report now and freeze the result."""
    report = generate_report(report_type, filters or {})
    return SavedReport.objects.create(
        name=name.strip(),
        report_type=report_type,
        filters=report["filters"],   
        data=report,
        generated_by=user,
    )