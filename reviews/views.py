from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record as record_audit
from common.permissions import ADMIN_ROLES, IsAdmin, IsVendor

from .models import Review, ReviewReply
from .serializers import (
    ReviewCreateSerializer,
    ReviewReplyCreateSerializer,
    ReviewReplySerializer,
    ReviewSerializer,
    ReviewUpdateSerializer,
    ReviewVisibilitySerializer,
)
from .services import (
    check_eligibility,
    create_reply,
    create_review,
    rating_summary,
    resolve_target,
)


class ReviewPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


@extend_schema(
    tags=["reviews"],
    summary="Write a review (customers)",
    request=ReviewCreateSerializer,
    responses={201: ReviewSerializer},
    description=(
        "Allowed only after the customer's order containing the product has "
        "been delivered, and only once per item."
    ),
)
class ReviewCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = create_review(customer=request.user, **serializer.validated_data)
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["reviews"],
    summary="Reviews of one item (public)",
    description="Newest first, with the average rating and review count in 'summary'.",
)
class ReviewListView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = (AllowAny,)
    authentication_classes = ()  # an expired token must not break a public page
    pagination_class = ReviewPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Review.objects.none()
        self.field, self.target = resolve_target(
            self.kwargs["kind"], self.kwargs["pk"]
        )
        return Review.objects.filter(
            **{self.field: self.target}, is_visible=True
        ).select_related("customer").prefetch_related("replies__author")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data["summary"] = rating_summary(self.field, self.target)
        return response


@extend_schema(tags=["reviews"], summary="My reviews")
class MyReviewListView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = ReviewPagination

    def get_queryset(self):
        return Review.objects.filter(customer=self.request.user).select_related("customer").prefetch_related("replies__author")


@extend_schema(
    tags=["reviews"],
    summary="Edit or delete my review",
)
class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "patch", "delete", "head", "options")

    def get_queryset(self):
        # Someone else's review behaves as if it does not exist (404).
        return Review.objects.filter(customer=self.request.user).select_related("customer").prefetch_related("replies__author")

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ReviewUpdateSerializer
        return ReviewSerializer

    def update(self, request, *args, **kwargs):
        review = self.get_object()
        serializer = ReviewUpdateSerializer(review, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ReviewSerializer(review).data)


@extend_schema(
    tags=["reviews"],
    summary="Can I review this?",
    parameters=[
        OpenApiParameter("kind", str, description="product, service or pet."),
        OpenApiParameter("id", int, description="The item's id."),
    ],
    description="Lets the frontend decide whether to show the review form.",
)
class ReviewEligibilityView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        _, target = resolve_target(
            request.query_params.get("kind", ""), request.query_params.get("id")
        )
        allowed, reason = check_eligibility(
            request.user, request.query_params["kind"], target
        )
        return Response({"can_review": allowed, "reason": reason})


@extend_schema(
    tags=["reviews"],
    summary="Hide or restore a review (administrators)",
    request=ReviewVisibilitySerializer,
    responses={200: ReviewSerializer},
)
class AdminReviewVisibilityView(APIView):
    permission_classes = (IsAdmin,)

    def patch(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        serializer = ReviewVisibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review.is_visible = serializer.validated_data["is_visible"]
        review.save(update_fields=["is_visible", "updated_at"])

        record_audit(
            actor=request.user,
            action="review.restored" if review.is_visible else "review.hidden",
            target=review,
            details={},
        )
        return Response(ReviewSerializer(review).data)


@extend_schema_view(
    get=extend_schema(tags=["reviews"], summary="Replies under a review (public)"),
    post=extend_schema(
        tags=["reviews"],
        summary="Reply to a review (vendors only)",
        request=ReviewReplyCreateSerializer,
        responses={201: ReviewReplySerializer},
        description=(
            "Only authenticated vendors can post a reply. "
            "The vendor must own the business associated with the reviewed item."
        ),
    ),
)
class ReviewReplyListCreateView(generics.ListCreateAPIView):
    serializer_class = ReviewReplySerializer
    pagination_class = ReviewPagination

    def initialize_request(self, request, *args, **kwargs):
        self._request_method = request.method
        return super().initialize_request(request, *args, **kwargs)

    def get_authenticators(self):
        # Reading is public and ignores tokens (an expired one must not break
        # the page); posting needs a login.
        if self._request_method == "GET":
            return []
        return super().get_authenticators()

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsVendor()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ReviewReply.objects.none()
        review = get_object_or_404(Review, pk=self.kwargs["pk"], is_visible=True)
        return review.replies.select_related("author")

    def create(self, request, *args, **kwargs):
        serializer = ReviewReplyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reply = create_reply(
            author=request.user,
            review_id=kwargs["pk"],
            body=serializer.validated_data["body"],
        )
        return Response(ReviewReplySerializer(reply).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["reviews"], summary="Delete a reply (author or admin)")
class ReviewReplyDeleteView(generics.DestroyAPIView):
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        replies = ReviewReply.objects.all()
        if self.request.user.role in ADMIN_ROLES:
            return replies
        # Someone else's reply behaves as if it does not exist (404).
        return replies.filter(author=self.request.user)