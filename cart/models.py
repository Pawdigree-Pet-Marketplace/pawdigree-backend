from django.db import models
from django.conf import settings
from django.db.models import Q

from common.models import TimeStampedModel
from products.models import Product

#Limits applied to the cart 
MAX_QUANTITY_PER_ITEM = 99
MAX_LINES_PER_CART = 50

class Cart(TimeStampedModel):
    """Each customer has exactly one cart"""
    
    #Have only one cart per customer, reject more than one cart
    customer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart"
    )
    
    def __str__(self):
        return f"Cart of {self.customer}"
    
    
class CartItem(TimeStampedModel):
    """One product in a cart, with how many the customer wants.
    The price is deliberately not stored here. It is read from the product
    every time, so the cart always shows the current price."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="item")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    
    class Meta:
        # Lines appear in the order they were added.
        ordering = ("created_at", "id")
        constraints = (
            # A product appears once per cart. Adding it again raises the
            # quantity instead of creating a second row.
            models.UniqueConstraint(
                fields=["cart", "product"],
                name="unique_product_per_cart",
            ),
            # the quantity of an item in a cart cannot be less than 1
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="cart_item_quantity_at_least_one",
            ),
        )
        
    def __str__(self):
        return f"{self.quantity} x {self.product}"