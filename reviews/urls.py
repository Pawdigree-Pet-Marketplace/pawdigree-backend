from django.urls import path

from .views import (
    AdminReviewVisibilityView,
    MyReviewListView,
    ReviewCreateView,
    ReviewDetailView,
    ReviewEligibilityView,
    ReviewListView,
)

urlpatterns = [
    path("", ReviewCreateView.as_view(), name="review-create"),
    path("mine/", MyReviewListView.as_view(), name="review-mine"),
    path("can-review/", ReviewEligibilityView.as_view(), name="review-can-review"),
    path("<int:pk>/", ReviewDetailView.as_view(), name="review-detail"),
    path("<int:pk>/visibility/", AdminReviewVisibilityView.as_view(), name="review-visibility"),
    path("<str:kind>/<int:pk>/", ReviewListView.as_view(), name="review-list"),
]