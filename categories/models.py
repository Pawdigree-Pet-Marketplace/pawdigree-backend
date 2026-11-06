
from django.db import models
from django.utils.text import slugify

from common.models import TimeStampedModel


class Category(TimeStampedModel):
    """A marketplace category managed by administrators."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    class Kind(models.TextChoices):
        GENERAL = "general", "General"
        PETS = "pets", "Pets"
        MERCHANDISE = "merchandise", "Merchandise"
        SERVICES = "services", "Services"

    # The kind of category, which determines the type of products or services
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.GENERAL,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "marketplace_category"
        ordering = ("name",)

    def save(self, *args, **kwargs):
        base_slug = slugify(self.name) or "category"

        # Generate a new slug when creating or renaming a category.
        should_generate_slug = not self.slug

        if self.pk:
            original = Category.objects.filter(pk=self.pk).only(
                "name"
            ).first()

            if original and original.name != self.name:
                should_generate_slug = True

        if should_generate_slug:
            slug = base_slug
            counter = 2

            while Category.objects.filter(slug=slug).exclude(
                pk=self.pk
            ).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
