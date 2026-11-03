from django.db import models

from businesses.models import Business
from categories.models import Category
from common.models import TimeStampedModel
from common.validators import validate_image_upload


class Product(TimeStampedModel):
    """Physical merchandise sold by a business on Pawdigree."""

    business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="products",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name
    @property
    def is_available(self):
        return self.is_active and self.stock_quantity > 0


class ProductImage(models.Model):
    """An image belonging to a physical product."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(
        upload_to="products/%Y/%m/",
        validators=[validate_image_upload],
    )
    alt_text = models.CharField(max_length=150, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "id")

    def __str__(self):
        return f"Image for {self.product.name}"
