import uuid
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import User
from businesses.models import Business
from products.models import Product

from .models import MAX_LINES_PER_CART, MAX_QUANTITY_PER_ITEM, Cart, CartItem

TWO_PLACES = Decimal("0.01")

# The header a guest's browser sends to say which cart is theirs.
GUEST_HEADER = "X-Cart-Token"


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
    """The same rule as visible_products(), for one product already loaded."""
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
    # Only set when a guest cart is created or used for adding.
    cart_token: uuid.UUID | None = None


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
    Only lines that can really be bought count toward the total."""
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


# ---- Who owns the cart ----------------------------------------------------
@dataclass(frozen=True)
class CartOwner:
    """Who a cart belongs to: a logged-in customer, or a guest's token."""

    customer: User | None = None
    guest_token: uuid.UUID | None = None


def guest_token_from_request(request):
    """The token in the request header, or None if it is missing or malformed."""
    raw = request.headers.get(GUEST_HEADER, "")
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return None


def owner_from_request(request):
    """A logged-in user is identified by the account. Others, by the token."""
    if request.user.is_authenticated:
        return CartOwner(customer=request.user)
    return CartOwner(guest_token=guest_token_from_request(request))


def _check_owner(owner):
    """The view checks the role. This keeps the services safe on their own."""
    if owner.customer is not None and owner.customer.role != User.Role.CUSTOMER:
        raise PermissionDenied("Only customers have a cart.")


def _find_cart(owner, lock=False):
    """The owner's existing cart, or None. Never creates anything.
    lock=True holds a database lock until the transaction ends, so two
    requests for the same cart take turns. Call it inside transaction.atomic()."""
    if owner.customer is not None:
        lookup = {"customer": owner.customer}
    elif owner.guest_token is not None:
        lookup = {"guest_token": owner.guest_token}
    else:
        return None

    queryset = Cart.objects.filter(**lookup)
    if lock:
        queryset = queryset.select_for_update()
    return queryset.first()


def _get_or_create_cart(owner):
    """The owner's cart, locked, creating one if needed. Use inside atomic()."""
    cart = _find_cart(owner, lock=True)
    if cart is not None:
        return cart

    if owner.customer is not None:
        # get_or_create copes with two first adds arriving at the same moment.
        cart, _ = Cart.objects.get_or_create(customer=owner.customer)
        return Cart.objects.select_for_update().get(pk=cart.pk)

    # A guest with no cart yet. The token is always made by the server, even
    # if the client sent one that matches nothing.
    return Cart.objects.create(guest_token=uuid.uuid4())


def get_cart_summary(owner):
    """The owner's cart, calculated fresh. Reading never creates a cart."""
    cart = _find_cart(owner)
    if cart is None:
        return build_cart_summary([])

    items = (
        cart.items
        .select_related("product__business", "product__category")
        .prefetch_related("product__images")
    )
    return build_cart_summary(items)


def add_to_cart(owner, product_id, quantity):
    """Add a product to the cart, or raise its quantity if it's already there.

    Returns (cart, created). Everything happens in one transaction, so a
    refused request leaves nothing behind, not even a new guest cart.
    """
    _check_owner(owner)

    with transaction.atomic():
        cart = _get_or_create_cart(owner)

        # Only products customers can see. A hidden or missing product looks
        # the same: it doesn't exist as far as the visitor is concerned.
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
            CartItem.objects.create(cart=cart, product=product, quantity=quantity)
            return cart, True

        item.quantity = new_quantity
        item.save(update_fields=["quantity", "updated_at"])
        return cart, False
    
    
def merge_guest_cart(customer, guest_token):
    """Move a guest cart's lines into the customer's cart, then delete it.
    Merging never fails: lines that can't be kept are skipped. Quantities are
    added together but capped by stock and by the per-product limit, and the
    customer's own quantity is never lowered."""
    owner = CartOwner(customer=customer)
    _check_owner(owner)

    if guest_token is None:
        return

    # A cheap check first, so nothing is created when there is nothing to merge.
    if not Cart.objects.filter(guest_token=guest_token).exists():
        return

    with transaction.atomic():
        # Always the same lock order: the customer's cart first, then the
        # guest cart. Two merges can't block each other forever.
        cart = _get_or_create_cart(owner)
        guest_cart = (
            Cart.objects.select_for_update().filter(guest_token=guest_token).first()
        )
        if guest_cart is None:
            return  # another request merged it in the meantime

        existing = {item.product_id: item for item in cart.items.all()}
        guest_items = guest_cart.items.select_related(
            "product__business", "product__category"
        )

        for guest_item in guest_items:
            product = guest_item.product

            if not product_is_visible(product) or product.stock_quantity == 0:
                continue

            limit = min(product.stock_quantity, MAX_QUANTITY_PER_ITEM)
            current = existing.get(product.pk)

            if current is None:
                if len(existing) >= MAX_LINES_PER_CART:
                    continue
                existing[product.pk] = CartItem.objects.create(
                    cart=cart,
                    product=product,
                    quantity=min(guest_item.quantity, limit),
                )
                continue

            merged = min(current.quantity + guest_item.quantity, limit)
            # Only ever raise the customer's quantity.
            if merged > current.quantity:
                current.quantity = merged
                current.save(update_fields=["quantity", "updated_at"])

        guest_cart.delete()