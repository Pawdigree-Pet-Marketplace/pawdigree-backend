from dataclasses import dataclass
from decimal import Decimal

from businesses.models import Business
from products.models import Product

from .models import MAX_QUANTITY_PER_ITEM, CartItem

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