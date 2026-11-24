from django.db.models import Exists, OuterRef, Subquery
from rest_framework.exceptions import NotFound

from pets.models import Pet
from products.models import Product

from .models import Favourite


def add_favourite(customer, pet_id):
    """Save a pet for a customer. Saving it twice is harmless.

    Returns (favourite, created). Raises NotFound if the pet cannot be
    seen by the public, the same rule as the public pet list.
    """
    try:
        pet = Pet.objects.publicly_visible().get(pk=pet_id)
    except Pet.DoesNotExist:
        raise NotFound("This pet is not available.")

    return Favourite.objects.get_or_create(customer=customer, pet=pet)


def remove_favourite(customer, pet_id):
    """Remove a favourite. Nothing to remove is not an error."""
    Favourite.objects.filter(customer=customer, pet_id=pet_id).delete()


def favourite_pets(customer):
    """The customer's saved pets that are still publicly visible, newest first."""
    mine = Favourite.objects.filter(customer=customer, pet=OuterRef("pk"))
    return (
        Pet.objects.publicly_visible()
        .filter(Exists(mine))
        .annotate(favourited_at=Subquery(mine.values("created_at")[:1]))
        .order_by("-favourited_at", "-pet_id")
        .select_related("business")
        .prefetch_related("images")
    )


def favourite_pet_ids(customer):
    return list(favourite_pets(customer).values_list("pet_id", flat=True))


#------------------Products-------------------------
def add_favourite_product(customer, product_id):
    """Save a product for a customer. Saving it twice is harmless.

    Returns (favourite, created). Raises NotFound if customers cannot see
    the product, the same rule as the public product list.
    """
    try:
        product = Product.objects.publicly_visible().get(pk=product_id)
    except Product.DoesNotExist:
        raise NotFound("This product is not available.")

    return Favourite.objects.get_or_create(customer=customer, product=product)


def remove_favourite_product(customer, product_id):
    """Remove a favourite. Nothing to remove is not an error."""
    Favourite.objects.filter(customer=customer, product_id=product_id).delete()


def favourite_products(customer):
    """Saved products that are still publicly visible, newest first."""
    mine = Favourite.objects.filter(customer=customer, product=OuterRef("pk"))
    return (
        Product.objects.publicly_visible()
        .filter(Exists(mine))
        .annotate(favourited_at=Subquery(mine.values("created_at")[:1]))
        .order_by("-favourited_at", "-pk")
        .select_related("business", "category")
        .prefetch_related("images")
    )


def favourite_product_ids(customer):
    return list(favourite_products(customer).values_list("pk", flat=True))