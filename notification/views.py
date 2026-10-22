from django.shortcuts import render
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer, UnreadCountSerializer


class NotificationPagination(PageNumberPagination):
    page_size = 20


class UserNotificationsMixin:
    """Every view only ever sees the caller's own notifications."""

    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


@extend_schema(
    tags=["notifications"],
    summary="List my notifications",
    description="Newest first. Use ?is_read=false to see only unread ones.",
)
class NotificationListView(UserNotificationsMixin, generics.ListAPIView):
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == "true")
        return queryset


@extend_schema(
    tags=["notifications"],
    summary="Unread notification count",
    responses=UnreadCountSerializer,
)
class UnreadCountView(UserNotificationsMixin, generics.GenericAPIView):
    serializer_class = UnreadCountSerializer

    def get(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({"unread": count})


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
    summary="Mark all my notifications as read",
    request=None,
    responses=UnreadCountSerializer,
)
class MarkAllReadView(UserNotificationsMixin, generics.GenericAPIView):
    serializer_class = UnreadCountSerializer

    def post(self, request):
        # update() skips save(), so auto_now does not run: set it ourselves.
        self.get_queryset().filter(is_read=False).update(
            is_read=True,
            updated_at=timezone.now(),
        )
        return Response({"unread": 0})
