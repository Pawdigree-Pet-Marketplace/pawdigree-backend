from notification.models import Notification
from notification.services import create_notification

from .models import AdoptionApplication

T = Notification.Type


def _load(application_id):
    return AdoptionApplication.objects.select_related(
        "pet__business__vendor", "customer", "decided_by"
    ).get(pk=application_id)


def _to_vendor(application, ntype, message, key=None):
    business = application.pet.business
    create_notification(
        business.vendor, ntype, message,
        reference_id=application.pk, reference_type="adoption",
        business=business, event_key=key,
    )


def _to_customer(application, message, key=None):
    create_notification(
        application.customer, T.ADOPTION_UPDATE, message,
        reference_id=application.pk, reference_type="adoption", event_key=key,
    )


def notify_application_submitted(application_id):
    application = _load(application_id)
    name = application.pet.name
    _to_vendor(
        application, T.ADOPTION_NEW,
        f"New adoption application for {name}.",
        f"adoption-new:{application.pk}",
    )
    _to_customer(
        application,
        f"Your application for {name} was submitted. You'll be notified of updates.",
        f"adoption-submitted:{application.pk}",
    )


def notify_info_requested(application_id):
    application = _load(application_id)
    _to_customer(
        application,
        f"The vendor needs more information about your application for {application.pet.name}.",
    )


def notify_applicant_replied(application_id):
    application = _load(application_id)
    _to_vendor(
        application, T.ADOPTION_REPLY,
        f"The applicant replied about {application.pet.name}.",
    )


def notify_application_decided(application_id):
    application = _load(application_id)
    name = application.pet.name
    if application.status == AdoptionApplication.Status.APPROVED:
        message = f"Your application for {name} was approved."
    elif application.status == AdoptionApplication.Status.REJECTED:
        reason = f" Reason: {application.decision_reason}" if application.decision_reason else ""
        message = f"Your application for {name} was not approved.{reason}"
    else:
        return
    key = f"adoption-decision:{application.pk}:{application.status}"
    _to_customer(application, message, key)
    # When an admin decided, the vendor should hear about it too.
    vendor = application.pet.business.vendor
    if application.decided_by_id and application.decided_by_id != vendor.pk:
        _to_vendor(
            application, T.ADOPTION_UPDATE,
            f"An administrator {application.status.lower()} the application for {name}.",
            key,
        )