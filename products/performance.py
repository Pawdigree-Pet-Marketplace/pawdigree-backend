from decimal import Decimal

from django.db.models import (
    BooleanField,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce

from businesses.models import Business
from orders.models import Order, VendorOrder

LOW_STOCK_THRESHOLD = 5

# Vendor-order statuses that still count as a sale. CANCELLED is left out.
_S = VendorOrder.Status
COUNTED_STATUSES = (_S.PAID, _S.PROCESSING, _S.SHIPPED, _S.DELIVERED)

MONEY = DecimalField(max_digits=14, decimal_places=2)


def _sale_filter(prefix, date_from=None, date_to=None):
    """A Q that selects only the order items that count as a sale.
    `prefix` is the path from the model being annotated to OrderItem:
    "order_items__" from Product, "products__order_items__" from Business.
    """
    sale = Q(
        **{
            f"{prefix}vendor_order__order__status": Order.Status.PAID,
            f"{prefix}vendor_order__status__in": COUNTED_STATUSES,
        }
    )
    if date_from:
        sale &= Q(**{f"{prefix}vendor_order__order__created_at__date__gte": date_from})
    if date_to:
        sale &= Q(**{f"{prefix}vendor_order__order__created_at__date__lte": date_to})
    return sale


def _units_sold(prefix, sale):
    return Coalesce(Sum(F(f"{prefix}quantity"), filter=sale), 0)


def _revenue(prefix, sale):
    line_total = ExpressionWrapper(
        F(f"{prefix}quantity") * F(f"{prefix}unit_price"), output_field=MONEY
    )
    return Coalesce(
        Sum(line_total, filter=sale), Value(Decimal("0.00")), output_field=MONEY
    )


def with_product_performance(
    queryset,
    *,
    date_from=None,
    date_to=None,
    low_stock_threshold=LOW_STOCK_THRESHOLD,
):
    """Add units_sold, revenue and is_low_stock to a Product queryset."""
    prefix = "order_items__"
    sale = _sale_filter(prefix, date_from, date_to)
    return queryset.annotate(
        units_sold=_units_sold(prefix, sale),
        revenue=_revenue(prefix, sale),
        is_low_stock=ExpressionWrapper(
            Q(is_active=True, stock_quantity__lte=low_stock_threshold),
            output_field=BooleanField(),
        ),
    )


def with_business_performance(
    *,
    date_from=None,
    date_to=None,
    low_stock_threshold=LOW_STOCK_THRESHOLD,
):
    """Merchandise businesses with their sales and stock totals."""
    prefix = "products__order_items__"
    sale = _sale_filter(prefix, date_from, date_to)
    return Business.objects.filter(
        business_type=Business.BusinessType.PRODUCT_SELLER
    ).annotate(
        products_count=Count("products", distinct=True),
        low_stock_count=Count(
            "products",
            filter=Q(
                products__is_active=True,
                products__stock_quantity__lte=low_stock_threshold,
            ),
            distinct=True,
        ),
        orders_count=Count(f"{prefix}vendor_order", filter=sale, distinct=True),
        units_sold=_units_sold(prefix, sale),
        revenue=_revenue(prefix, sale),
    )