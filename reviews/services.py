from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError


from accounts.models import User
from orders.models import OrderItem, VendorOrder
from pets.models import Pet
from products.models import Product
from services.models import Service
from adoptions.models import AdoptionApplication
from bookings.models import Booking

from notification.services import after_commit

from .models import Review, ReviewReply
from .notifications import notify_new_review, notify_review_reply

TARGETS = {
    "product": ("product", Product),
    "service": ("service", Service),
    "pet": ("pet", Pet),
}



def resolve_target(kind, target_id):
    """Return (field_name, object) or raise 404 / 400."""
    if kind not in TARGETS:
        raise ValidationError({"kind": f"Must be one of: {', '.join(TARGETS)}."})
    field, model = TARGETS[kind]
    return field, get_object_or_404(model, pk=target_id)


def _has_completed_purchase(customer, product):
    """True if one of the customer's vendor orders containing it was delivered."""
    return OrderItem.objects.filter(
        product=product,
        vendor_order__order__customer=customer,
        vendor_order__status=VendorOrder.Status.DELIVERED,
    ).exists()


def _has_completed_booking(customer, service):
    """A booking the vendor marked as completed."""
    return Booking.objects.filter(
        customer=customer, service=service, status=Booking.Status.COMPLETED
    ).exists()


def _has_approved_adoption(customer, pet):
    """An adoption application the vendor approved."""
    return AdoptionApplication.objects.filter(
        customer=customer, pet=pet, status=AdoptionApplication.Status.APPROVED
    ).exists()
    
    
def _has_completed_pet_deal(customer, pet):
    """Sale: the pet was delivered. Adoption: the application was approved."""
    if pet.listing_type == Pet.ListingType.SALE:
        return OrderItem.objects.filter(
            pet=pet,
            vendor_order__order__customer=customer,
            vendor_order__status=VendorOrder.Status.DELIVERED,
        ).exists()
    return _has_approved_adoption(customer, pet)


# kind -> (the "did they really complete it?" check, message if they didn't)
COMPLETION_CHECKS = {
    "product": (
        _has_completed_purchase,
        "You can review a product after it has been delivered to you.",
    ),
    "service": (
        _has_completed_booking,
        "You can review a service after your booking is completed.",
    ),
    "pet": (
        _has_completed_pet_deal,
        "You can review a pet after your purchase is delivered "
        "or your adoption is approved.",
    ),
}


def check_eligibility(customer, kind, target):
    """Return (allowed, reason). The reason is shown to the customer."""
    if customer.role != User.Role.CUSTOMER:
        return False, "Only customers can write reviews."

    field = TARGETS[kind][0]
    if Review.objects.filter(customer=customer, **{field: target}).exists():
        return False, "You have already reviewed this."

    completed, message = COMPLETION_CHECKS[kind]
    if not completed(customer, target):
        return False, message

    return True, ""


def create_review(*, customer, kind, target_id, rating, comment=""):
    field, target = resolve_target(kind, target_id)

    allowed, reason = check_eligibility(customer, kind, target)
    if not allowed:
        raise PermissionDenied(reason)

    try:
        with transaction.atomic():
            review = Review.objects.create(
                customer=customer, rating=rating, comment=comment, **{field: target}
            )
            after_commit(lambda: notify_new_review(review.pk))
            return review
    except IntegrityError:
        raise ValidationError("You have already reviewed this.")


def create_reply(*, author, review_id, body):
    """Customers and admins can reply to any visible review; a vendor only
    on reviews of their own business's items."""
    review = get_object_or_404(
        Review.objects.select_related(
            "customer", "product__business", "service__business", "pet__business"
        ),
        pk=review_id,
        is_visible=True,
    )
    body = (body or "").strip()
    if not body:
        raise ValidationError({"body": "Write something first."})

    if author.role == User.Role.VENDOR and review.business.vendor_id != author.pk:
        raise PermissionDenied(
            "Only the business that owns this item can reply as a vendor."
        )

    with transaction.atomic():
        reply = ReviewReply.objects.create(review=review, author=author, body=body)
        after_commit(lambda: notify_review_reply(reply.pk))
    return reply


def rating_summary(field, target):
    """Average (1 decimal, or None) and count of the visible reviews."""
    data = Review.objects.filter(**{field: target}, is_visible=True).aggregate(
        average=Avg("rating"), count=Count("id")
    )
    average = data["average"]
    return {
        "average_rating": round(average, 1) if average is not None else None,
        "review_count": data["count"],
    }
    
    
def with_ratings(queryset, field):
    """Add average_rating and review_count to every row in one query.
    Subqueries are used instead of Avg()/Count() joins, because the public
    service list already joins other tables and a second join could
    multiply rows and corrupt the numbers."""
    
    visible = Review.objects.filter(is_visible=True, **{field: OuterRef("pk")})
    per_item = visible.order_by().values(field)
    return queryset.annotate(
        average_rating=Subquery(per_item.annotate(a=Avg("rating")).values("a")),
        review_count=Coalesce(
            Subquery(per_item.annotate(c=Count("id")).values("c")), 0
        ),
    )