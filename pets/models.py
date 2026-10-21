from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.validators import validate_image_upload


class PetQuerySet(models.QuerySet):
    def publicly_visible(self):
        """Return approved, active pets that are available."""
        return self.filter(
            approved=True,
            is_active=True,
            adoption_status="AVAILABLE",
        )
        
    def pending_review(self):
        """Active listings waiting for an admin decision."""
        return self.filter(approved=False, is_active=True, rejection_reason="")
    

class Pet(models.Model):
    class Gender(models.TextChoices):
        MALE = 'MALE', 'Male'
        FEMALE = 'FEMALE', 'Female'
        UNKNOWN = 'UNKNOWN', 'Unknown'

    class Size(models.TextChoices):
        SMALL = 'SMALL', 'Small'
        MEDIUM = 'MEDIUM', 'Medium'
        LARGE = 'LARGE', 'Large'

    class AdoptionStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        PENDING = 'PENDING', 'Pending'
        ADOPTED = 'ADOPTED', 'Adopted'

    class ListingType(models.TextChoices):
        ADOPTION = "ADOPTION", "Adoption"
        SALE = "SALE", "For Sale"

    pet_id = models.AutoField(primary_key=True)

    # Connect to the vendor user model.
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pet_listing",
        limit_choices_to={"role": "VENDOR"},
    )

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="pet_listing",
    )

    listing_type = models.CharField(
        max_length=10,
        choices=ListingType.choices,
        default=ListingType.ADOPTION,
    )

    name = models.CharField(max_length=100)
    species = models.CharField(max_length=100, default="unknown")
    breed = models.CharField(max_length=100, blank=True)
    age = models.PositiveIntegerField(help_text="Age in months")
    gender = models.CharField(max_length=10, choices=Gender.choices)
    size = models.CharField(max_length=10, choices=Size.choices)
    description = models.TextField(blank=True)
    approved = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_pets",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price is required for pets listed for sale.",
    )
    adoption_status = models.CharField(
        max_length=10,
        choices=AdoptionStatus.choices,
        default=AdoptionStatus.AVAILABLE,
    )

    # Creation time is not editable; update time changes on every save.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PetQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at",]

    def clean(self):
        """A sale listing needs a positive price; an adoption must have none."""
        super().clean()

        if self.listing_type == self.ListingType.SALE:
            if self.price is None or self.price <= 0:
                raise ValidationError({
                    "price": (
                        "A sale listing must have a price greater than zero."
                    )
                })
        elif (
            self.listing_type == self.ListingType.ADOPTION
            and self.price is not None
        ):
            raise ValidationError({
                "price": "An adoption listing must not have a price."
            })

    def __str__(self):
        return f"{self.name} ({self.species})"
     
    @property
    def review_status(self):
        if self.approved:
            return "APPROVED"
        if self.rejection_reason:
            return "REJECTED"
        return "PENDING"
    
    
class PetImage(models.Model):
    image_id = models.AutoField(primary_key=True)
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE, related_name="images") 
    
    image = models.ImageField(
        upload_to="pets/",
        validators=[validate_image_upload],
    )  # or URLField if you store external URLs
    is_primary = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)  
    
    class Meta:
        ordering = ["position", "created_at"]
        
