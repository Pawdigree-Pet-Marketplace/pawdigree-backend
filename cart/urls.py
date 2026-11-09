from django.urls import path
from .views import CartItemCreateView, CartItemDetailView, CartMergeView, CartView

urlpatterns = [
    path("", CartView.as_view(), name="cart"),
    path("merge/", CartMergeView.as_view(), name="cart-merge"),
    path("items/<int:item_id>/", CartItemDetailView.as_view(), name="cart-item"),
    path("items/", CartItemCreateView.as_view(), name="cart-items"),
]