from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings

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
        
    pet_id = models.AutoField(primary_key=True)
    
    #connect to user.vendor model
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="pet_listing",
        limit_choices_to={"role": "VENDOR"},
        )
    
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="pet_listing")
    
    name = models.CharField(max_length=100)
    breed = models.CharField(max_length=100, blank=True)
    age = models.PositiveIntegerField(help_text="Age in months")
    gender = models.CharField(max_length=10, choices=Gender.choices)
    size = models.CharField(max_length=10, choices=Size.choices)
    description = models.TextField(blank=True)
    adoption_status = models.CharField(max_length=10, choices=AdoptionStatus.choices, default=AdoptionStatus.AVAILABLE)
    
    #time of creation is uneditable, time of update chenges to latest update
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-created_at"]
        
    # def clean(self):
    # errors = {}

    # if self.vendor_id and self.vendor.role != "VENDOR":
    #     errors["vendor"] = "Listings can only be created by vendors."

    # if self.business_id and self.vendor_id:
    #     if self.business.vendor_id != self.vendor_id:
    #         errors["business"] = "This vendor does not own this business."

    # if errors:
    #     raise ValidationError(errors)
            
    def __str__(self):
        return f"{self.name} ({self.species})"
     
     
class PetImage(models.Model):
    image_id = models.AutoField(primary_key=True)
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE, related_name="images") 
    
    image = models.ImageField(upload_to="pets/")  # or URLField if you store external URLs
    is_primary = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)  
    
    class Meta:
        ordering = ["position", "created_at"]
        
