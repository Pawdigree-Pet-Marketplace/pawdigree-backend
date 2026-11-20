import uuid

from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from businesses.models import Business

from .models import Notification
from .serializers import NotificationSerializer, UnreadCountSerializer

BUSINESS_PARAM = OpenApiParameter(
    "business",
    str,
    description=(
        "Vendors only: a business id. Leave it out for the whole vendor "
        "account (main dashboard)."
    ),
)


class NotificationPagination(PageNumberPagination):
    page_size = 20


class UserNotificationsMixin:
    """Every view only ever sees the caller's own notifications."""

    permission_classes = (IsAuthenticated,)

    def own_notifications(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user).select_related(
            "business"
        )

    def get_queryset(self):
        return self.own_notifications()

    def scoped(self, queryset):
        """Narrow to one business when ?business= is given."""
        raw = self.request.query_params.get("business")
        if not raw:
            return queryset

        user = self.request.user
        if user.role != User.Role.VENDOR:
            raise ValidationError({"business": "Only vendors can filter by business."})
        try:
            business_id = uuid.UUID(raw)
        except ValueError:
            raise ValidationError({"business": "Not a valid business id."})
        # Someone else's business looks the same as one that doesn't exist.
        if not Business.objects.filter(pk=business_id, vendor=user).exists():
            raise NotFound("Business not found.")
        return queryset.filter(business_id=business_id)

    def unread_payload(self, queryset):
        payload = {"unread": queryset.filter(is_read=False).count()}
        if self.request.user.role == User.Role.VENDOR:
            # Per-business badges for the business switcher (whole account).
            rows = (
                Notification.objects.filter(user=self.request.user, is_read=False)
                .order_by()
                .values("business_id")
                .annotate(n=Count("pk"))
            )
            payload["by_business"] = {
                (str(r["business_id"]) if r["business_id"] else "unassigned"): r["n"]
                for r in rows
            }
        return payload


def _parse_bool(value):
    lowered = value.lower()
    if lowered in ("true", "1"):
        return True
    if lowered in ("false", "0"):
        return False
    raise ValidationError({"is_read": "Use true or false."})


@extend_schema(
    tags=["notifications"],
    summary="List my notifications",
    description=(
        "Newest first. Filters: ?is_read=false, ?type=NEW_ORDER and, for "
        "vendors, ?business=<id>."
    ),
    parameters=[BUSINESS_PARAM],
)
class NotificationListView(UserNotificationsMixin, generics.ListAPIView):
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination

    def get_queryset(self):
        queryset = self.scoped(self.own_notifications())

        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            queryset = queryset.filter(is_read=_parse_bool(is_read))

        notification_type = self.request.query_params.get("type")
        if notification_type:
            if notification_type not in Notification.Type.values:
                raise ValidationError({"type": "Not a valid notification type."})
            queryset = queryset.filter(type=notification_type)
        return queryset


@extend_schema(
    tags=["notifications"],
    summary="Unread notification count",
    description=(
        "`unread` respects ?business=. Vendors also get `by_business`, the "
        "unread count of every business, for the business switcher."
    ),
    parameters=[BUSINESS_PARAM],
    responses=UnreadCountSerializer,
)
class UnreadCountView(UserNotificationsMixin, generics.GenericAPIView):
    serializer_class = UnreadCountSerializer

    def get(self, request):
        return Response(self.unread_payload(self.scoped(self.own_notifications())))


@extend_schema(
    tags=["notifications"],
    summary="Mark one notification as read",
    request=None,
    responses=NotificationSerializer,
)
class MarkReadView(UserNotificationsMixin, generics.GenericAPIView):
    serializer_class = NotificationSerializer

    def post(self, request, pk):
        notification = self.get_object()  # 404 if it isn't the caller's

        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read", "updated_at"])

        return Response(self.get_serializer(notification).data)


@extend_schema(
    tags=["notifications"],
    summary="Mark my notifications as read",
    description=(
        "Marks everything read, or only one business's notifications when "
        "?business= is given. Returns the unread counts afterwards."
    ),
    parameters=[BUSINESS_PARAM],
    request=None,
    responses=UnreadCountSerializer,
)
class MarkAllReadView(UserNotificationsMixin, generics.GenericAPIView):
    serializer_class = UnreadCountSerializer

    def post(self, request):
        queryset = self.scoped(self.own_notifications())
        # update() skips save(), so auto_now does not run: set it ourselves.
        queryset.filter(is_read=False).update(
            is_read=True, updated_at=timezone.now()
        )
        return Response(self.unread_payload(queryset))