from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError,
)

from accounts.models import User
from pets.models import Pet

from .models import ACTIVE_STATUSES, AdoptionApplication, AdoptionInfoMessage

ALREADY_APPLIED = 'You already have an open application for this pet.'


def create_adoption_application(customer, pet_id, data):
    """Create an application once the system checks pass.

    Raises NotFound if the pet cannot be applied for, and ValidationError
    if the customer already has an open application for it.
    """
    try:
        pet = Pet.objects.publicly_visible().get(pk=pet_id)
    except Pet.DoesNotExist:
        raise NotFound('This pet is not available.')

    already_applied = AdoptionApplication.objects.filter(
        customer=customer,
        pet=pet,
        status__in=ACTIVE_STATUSES,
    ).exists()
    if already_applied:
        raise ValidationError({'pet': ALREADY_APPLIED})

    try:
        with transaction.atomic():
            return AdoptionApplication.objects.create(
                customer=customer,
                pet=pet,
                **data,
            )
    except IntegrityError:
        # Two submits at the same moment: the database rule stopped the second.
        raise ValidationError({'pet': ALREADY_APPLIED})
    
    
def decide_adoption_application(
    application_id,
    actor,
    decision,
    decision_reason="",
):
    """Approve or reject an adoption application."""
    with transaction.atomic():
        try:
            application = (
                AdoptionApplication.objects
                .select_for_update()
                .select_related("pet__business")
                .get(pk=application_id)
            )
        except AdoptionApplication.DoesNotExist:
            raise NotFound("Adoption application not found.")

        is_admin = (
            actor.role in (User.Role.ADMIN, User.Role.SYSTEM_ADMIN)
            or actor.is_superuser
        )

        if not is_admin:
            if (
                actor.role != User.Role.VENDOR
                or application.pet.vendor_id != actor.pk
                or application.pet.business.vendor_id != actor.pk
            ):
                raise PermissionDenied(
                    "You can only decide applications for your own pets."
                )

        if application.status not in ACTIVE_STATUSES:
            raise ValidationError({
                "status": "This application has already been decided or closed."
            })

        pet = Pet.objects.select_for_update().get(
            pk=application.pet_id
        )

        if decision == AdoptionApplication.Status.APPROVED:
            if (
                not pet.approved
                or not pet.is_active
                or pet.adoption_status != Pet.AdoptionStatus.AVAILABLE
            ):
                raise ValidationError({
                    "pet": "This pet is no longer available for adoption."
                })

            pet.adoption_status = Pet.AdoptionStatus.ADOPTED
            pet.save(update_fields=["adoption_status", "updated_at"])

        application.status = decision
        application.decided_by = actor
        application.decided_at = timezone.now()
        application.decision_reason = decision_reason
        application.save(
            update_fields=[
                "status",
                "decided_by",
                "decided_at",
                "decision_reason",
                "updated_at",
            ]
        )

        return application
    
    
    
def request_adoption_info(application_id, actor, message):
    """A vendor asks the applicant for more information.

    The application moves from PENDING to INFO_REQUESTED and the question
    is saved on it. Another vendor's application behaves as if it does not
    exist (NotFound), so its existence is not revealed.
    """
    # The view already checks the role. This keeps the function safe if it
    # is ever called from somewhere else.
    if actor.role != User.Role.VENDOR:
        raise PermissionDenied('Only vendors can request information.')

    with transaction.atomic():
        try:
            # Search only among applications for this vendor's own pets, and
            # lock the row, so a reply or a decision can't change the status
            # while this request is half done.
            application = (
                AdoptionApplication.objects
                .select_for_update(of=('self',))
                .select_related('pet', 'customer')
                .get(
                    pk=application_id,
                    pet__vendor=actor,
                    pet__business__vendor=actor,
                )
            )
        except AdoptionApplication.DoesNotExist:
            raise NotFound('Adoption application not found.')

        # Checked after the lock, so the status can't change underneath us.
        if application.status == AdoptionApplication.Status.INFO_REQUESTED:
            raise ValidationError({
                'status': 'You are already waiting for the applicant to reply.'
            })
        if application.status != AdoptionApplication.Status.PENDING:
            raise ValidationError({
                'status': 'Information can only be requested for a pending '
                          'application.'
            })

        # There is no point asking about a pet that is gone.
        pet = application.pet
        if (
            not pet.is_active
            or pet.adoption_status != Pet.AdoptionStatus.AVAILABLE
        ):
            raise ValidationError({'pet': 'This pet is no longer available.'})

        # The server decides the author and the kind. The client only
        # sends the text.
        AdoptionInfoMessage.objects.create(
            application=application,
            author=actor,
            kind=AdoptionInfoMessage.Kind.REQUEST,
            body=message,
        )

        application.status = AdoptionApplication.Status.INFO_REQUESTED
        application.save(update_fields=['status', 'updated_at'])

        return application
    

def reply_to_info_request(application_id, actor, message):
    """The applicant answers a vendor's request for information.

    The application moves from INFO_REQUESTED back to PENDING and the reply
    is saved on it. Someone else's application behaves as if it does not
    exist (NotFound).
    """
    if actor.role != User.Role.CUSTOMER:
        raise PermissionDenied('Only the applicant can reply.')

    with transaction.atomic():
        try:
            # Only this customer's own applications, row locked, so a
            # decision made at the same moment can't be overwritten.
            application = (
                AdoptionApplication.objects
                .select_for_update(of=('self',))
                .select_related('pet')
                .get(pk=application_id, customer=actor)
            )
        except AdoptionApplication.DoesNotExist:
            raise NotFound('Adoption application not found.')

        # Checked after the lock. If the vendor approved or rejected the
        # application first, the reply is refused.
        if application.status != AdoptionApplication.Status.INFO_REQUESTED:
            raise ValidationError({
                'status': 'There is no information request to reply to.'
            })

        AdoptionInfoMessage.objects.create(
            application=application,
            author=actor,
            kind=AdoptionInfoMessage.Kind.REPLY,
            body=message,
        )

        # Back to PENDING: the vendor can read the answer, then decide or
        # ask again.
        application.status = AdoptionApplication.Status.PENDING
        application.save(update_fields=['status', 'updated_at'])

        return application