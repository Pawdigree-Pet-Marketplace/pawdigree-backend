from notification.models import Notification
from notification.services import create_notification

from .models import Review, ReviewReply

T = Notification.Type

RELATED = (
    "customer",
    "product__business__vendor",
    "service__business__vendor",
    "pet__business__vendor",
)


def notify_new_review(review_id):
    review = Review.objects.select_related(*RELATED).get(pk=review_id)
    business = review.business
    create_notification(
        business.vendor, T.NEW_REVIEW,
        f"New {review.rating}★ review on {review.target.name}.",
        reference_id=review.target_pk, reference_type=review.target_kind,
        business=business, event_key=f"new-review:{review.pk}",
    )


def notify_review_reply(reply_id):
    """Everyone in the conversation except the person who just replied."""
    reply = ReviewReply.objects.select_related(
        "author", *(f"review__{r}" for r in RELATED)
    ).get(pk=reply_id)
    review = reply.review
    business = review.business
    vendor = business.vendor

    for recipient in {review.customer_id: review.customer, vendor.pk: vendor}.values():
        if recipient.pk == reply.author_id:
            continue
        create_notification(
            recipient, T.REVIEW_REPLY,
            f"New reply on the review of {review.target.name}.",
            reference_id=review.target_pk, reference_type=review.target_kind,
            business=business if recipient.pk == vendor.pk else None,
            event_key=f"review-reply:{reply.pk}",
        )