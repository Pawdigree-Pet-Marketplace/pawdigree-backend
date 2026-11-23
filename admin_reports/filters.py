import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from accounts.models import User
from pets.models import Pet

MAX_RANGE_DAYS = 366
DEFAULT_RANGE_DAYS = 30


REPORT_TZ = ZoneInfo(
    getattr(settings, "REPORT_TIME_ZONE", settings.BOOKING_TIME_ZONE)
)

# Which filters each report understands. Anything else is rejected with a
# 400 instead of being silently ignored, so a filter never looks applied
# when it was not.
_COMMON = {"date_from", "date_to", "group_by"}
REPORT_FILTERS = {
    "overview": _COMMON,
    "users": _COMMON | {"role", "status"},
    "pets": _COMMON | {"listing_type", "species", "status", "business"},
    "product-sales": _COMMON | {"category", "business"},
    "pet-sales": _COMMON | {"species", "business"},
}

# "status" means a different thing in each report.
STATUS_CHOICES = {
    "users": User.AccountStatus.values,
    "pets": Pet.AdoptionStatus.values,
}


class ReportFilterSerializer(serializers.Serializer):
    """Every filter any report accepts. parse_filters() narrows them."""

    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    group_by = serializers.ChoiceField(
        choices=("day", "week", "month"), default="day"
    )
    category = serializers.IntegerField(required=False, min_value=1)
    business = serializers.UUIDField(required=False)
    status = serializers.CharField(required=False, max_length=20)
    listing_type = serializers.ChoiceField(
        choices=Pet.ListingType.choices, required=False
    )
    species = serializers.CharField(required=False, max_length=100)
    role = serializers.ChoiceField(choices=User.Role.choices, required=False)
    export = serializers.ChoiceField(choices=("xlsx", "pdf"), required=False)


@dataclass(frozen=True)
class ReportFilters:
    """Validated filters with the date range already resolved."""

    date_from: date
    date_to: date
    group_by: str = "day"
    category: int | None = None
    business: uuid.UUID | None = None
    status: str | None = None
    listing_type: str | None = None
    species: str | None = None
    role: str | None = None

    @property
    def start(self):
        """First instant of date_from in the report time zone."""
        return datetime.combine(self.date_from, time.min, tzinfo=REPORT_TZ)

    @property
    def end(self):
        """First instant AFTER date_to, so the range is [start, end)."""
        return datetime.combine(
            self.date_to + timedelta(days=1), time.min, tzinfo=REPORT_TZ
        )

    def as_dict(self):
        """JSON-safe form, with unused filters left out."""
        out = {}
        for key, value in asdict(self).items():
            if value is None:
                continue
            if isinstance(value, date):
                value = value.isoformat()
            elif isinstance(value, uuid.UUID):
                value = str(value)
            out[key] = value
        return out


def parse_filters(report_type, raw):
    """Validate raw query params / saved filters for one report."""
    serializer = ReportFilterSerializer(data=raw)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    allowed = REPORT_FILTERS[report_type]
    unsupported = {
        name: "This filter is not available for this report."
        for name in serializer.fields
        if name in raw and name not in allowed and name != "export"
    }
    if unsupported:
        raise serializers.ValidationError(unsupported)

    status = data.get("status")
    if status and status not in STATUS_CHOICES.get(report_type, ()):
        raise serializers.ValidationError({"status": "Not a valid status."})

    today = timezone.localtime(timezone.now(), REPORT_TZ).date()
    date_to = data.get("date_to", today)
    date_from = data.get("date_from", date_to - timedelta(days=DEFAULT_RANGE_DAYS - 1))
    if date_from > date_to:
        raise serializers.ValidationError({"date_from": "Must not be after date_to."})
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise serializers.ValidationError({"date_to": f"The range can be at most {MAX_RANGE_DAYS} days."})

    return ReportFilters(
        date_from=date_from,
        date_to=date_to,
        group_by=data["group_by"],
        category=data.get("category"),
        business=data.get("business"),
        status=status or None,
        listing_type=data.get("listing_type"),
        species=(data.get("species") or "").strip() or None,
        role=data.get("role"),
    )