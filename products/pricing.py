from decimal import Decimal

from businesses.models import Business

TWO_PLACES = Decimal("0.01")


def unavailable_reason(product, quantity):
    """Return why a product can't be bought in this quantity, or None."""
    business = product.business
    if (
        not product.is_active
        or not product.category.is_active
        or not business.is_active
        or business.verification_status
        != Business.VerificationStatus.APPROVED
    ):
        return "not_available"

    if product.stock_quantity == 0:
        return "out_of_stock"

    if quantity > product.stock_quantity:
        return "insufficient_stock"

    return None


def calculate_cart_total(items):
    """Work out cart lines and the total from (product, quantity) pairs.

    Prices come from the products as they are now, so a price change after
    adding to the cart is reflected. Lines that can't be bought are flagged
    and count as 0.00, so the line totals always add up to the total.
    Pass products loaded with select_related("category", "business").
    """
    lines = []
    total = Decimal("0.00")

    for product, quantity in items:
        if not isinstance(quantity, int) or quantity < 1:
            raise ValueError("Quantity must be a whole number of at least 1.")

        reason = unavailable_reason(product, quantity)
        if reason is None:
            line_total = (product.price * quantity).quantize(TWO_PLACES)
        else:
            line_total = Decimal("0.00")

        total += line_total
        lines.append({
            "product_id": product.id,
            "name": product.name,
            "unit_price": product.price,
            "quantity": quantity,
            "line_total": line_total,
            "available": reason is None,
            "unavailable_reason": reason,
        })

    return {"lines": lines, "total": total}