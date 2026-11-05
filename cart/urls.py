from django.urls import path
from .views import CartMergeView, CartView

urlpatterns = [
    path("", CartView.as_view(), name="cart"),
    path("merge/", CartMergeView.as_view(), name="cart-merge"),
]