from dataclasses import dataclass
from decimal import Decimal

from businesses.models import Business
from products.models import Product

from .models import MAX_LINES_PER_CART, MAX_QUANTITY_PER_ITEM, Cart, CartItem

from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import User

TWO_PLACES = Decimal("0.01")


def visible_products():
    """Products a customer can see, as a database query.
    The product, its category and its business must all be active, and the business must be approved."""
    return Product.objects.filter(
        is_active=True,
        category__is_active=True,
        business__is_active=True,
        business__verification_status=Business.VerificationStatus.APPROVED,
    )
    
def product_is_visible(product):
    """The same rule as visible_products(), for one product already loaded.
    Both must stay in step. A test compares them. """
    business = product.business
    return (
        product.is_active
        and product.category.is_active
        and business.is_active
        and business.verification_status == Business.VerificationStatus.APPROVED
    )
    
    
@dataclass
class CartLine:
    """One line of the cart, with everything calculated by the server."""

    item: CartItem
    line_total: Decimal
    available: bool
    issue: str | None
    max_quantity: int


@dataclass
class CartSummary:
    lines: list
    total_quantity: int
    total: Decimal
    has_unavailable_items: bool
    

def describe_line(item):
    """Why a line can't be bought as it stands, or None if it can."""
    product = item.product

    if not product_is_visible(product):
        return "This product is no longer available."
    if product.stock_quantity == 0:
        return "This product is out of stock."
    if item.quantity > product.stock_quantity:
        return f"Only {product.stock_quantity} left in stock."
    return None


def build_cart_summary(items):
    """Work out every line and the cart total from the cart's items.
    Only lines that can really be bought count toward the total, so the
    customer never sees a price for something they can't get."""
    lines = []
    total = Decimal("0.00")
    total_quantity = 0

    for item in items:
        product = item.product
        issue = describe_line(item)
        available = issue is None

        # Decimal times a whole number is exact, so there are no rounding errors.
        line_total = (product.price * item.quantity).quantize(TWO_PLACES)

        if available:
            total += line_total
            total_quantity += item.quantity

        if product_is_visible(product):
            max_quantity = min(product.stock_quantity, MAX_QUANTITY_PER_ITEM)
        else:
            max_quantity = 0

        lines.append(
            CartLine(
                item=item,
                line_total=line_total,
                available=available,
                issue=issue,
                max_quantity=max_quantity,
            )
        )

    return CartSummary(
        lines=lines,
        total_quantity=total_quantity,
        total=total.quantize(TWO_PLACES),
        has_unavailable_items=any(not line.available for line in lines),
    )
    

def get_cart_summary(customer):
    """The customer's cart, calculated fresh from the database."""
    items = (
        CartItem.objects.filter(cart__customer=customer)
        .select_related("product__business", "product__category")
        .prefetch_related("product__images")
    )
    return build_cart_summary(items)


def _require_customer(user):
    """Checks for user role to be customer, raises PermissionDenied if not."""
    if user.role != User.Role.CUSTOMER:
        raise PermissionDenied("Only customers have a cart.")


def add_to_cart(customer, product_id, quantity):
    """Add a product to the cart, or raise its quantity if it's already there.
    Returns (item, created). Everything happens in one transaction, so a
    refused request leaves nothing behind, not even an empty cart. """
    _require_customer(customer)

    with transaction.atomic():
        cart, _ = Cart.objects.get_or_create(customer=customer)

        # Lock the cart row until the transaction ends. Two simultaneous adds
        # take turns, so neither can read a stale quantity.
        cart = Cart.objects.select_for_update().get(pk=cart.pk)

        # Only products customers can see. A hidden or missing product looks
        # the same: it doesn't exist as far as the customer is concerned.
        try:
            product = visible_products().get(pk=product_id)
        except Product.DoesNotExist:
            raise NotFound("This product is not available.")

        if product.stock_quantity == 0:
            raise ValidationError({"product": "This product is out of stock."})

        item = CartItem.objects.filter(cart=cart, product=product).first()
        existing = item.quantity if item else 0
        new_quantity = existing + quantity

        if new_quantity > MAX_QUANTITY_PER_ITEM:
            raise ValidationError({
                "quantity": (
                    f"You can have at most {MAX_QUANTITY_PER_ITEM} of one "
                    "product in your cart."
                )
            })

        if new_quantity > product.stock_quantity:
            message = f"Only {product.stock_quantity} in stock."
            if existing:
                message += f" You already have {existing} in your cart."
            raise ValidationError({"quantity": message})

        if item is None:
            if cart.items.count() >= MAX_LINES_PER_CART:
                raise ValidationError({
                    "product": (
                        f"Your cart can hold at most {MAX_LINES_PER_CART} "
                        "different products."
                    )
                })
            item = CartItem.objects.create(
                cart=cart, product=product, quantity=quantity
            )
            return item, True

        item.quantity = new_quantity
        item.save(update_fields=["quantity", "updated_at"])
        return item, False